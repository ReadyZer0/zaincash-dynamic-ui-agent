"""Connection ownership and transaction semantics, including Windows cleanup."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from evaluation.run import ledger_snapshot
from llm_agent import LLMConfig
from payment_assist import PaymentAssist
from server import DemoApp


class TrackedConnection(sqlite3.Connection):
    closed = False
    fail_decision_insert = False

    def close(self) -> None:
        super().close()
        self.closed = True

    def execute(self, sql, parameters=()):
        result = super().execute(sql, parameters)
        if self.fail_decision_insert and sql.startswith(
            "INSERT OR IGNORE INTO review_decisions"
        ):
            raise RuntimeError("synthetic failure after the advisory write")
        return result


class SQLiteLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "lifecycle.sqlite3"
        self.app = DemoApp(self.path, agent_config=LLMConfig(mode="offline"))
        self.session = self.app.bootstrap("demo_amina")["session"]
        self.original_connect = sqlite3.connect
        self.connections: list[TrackedConnection] = []
        self.fail_decision_insert = False

    def connect(self, *args, **kwargs):
        connection = self.original_connect(*args, **kwargs, factory=TrackedConnection)
        connection.fail_decision_insert = self.fail_decision_insert
        self.connections.append(connection)
        return connection

    def assert_connections_closed(self) -> None:
        self.assertTrue(self.connections)
        self.assertTrue(all(connection.closed for connection in self.connections))

    def prepare(self):
        _response, issued = self.app.dispatch_action(
            self.session,
            "OPEN_TRANSFER",
            {
                "recipient_id": "contact_ali_diaa",
                "amount_minor": 10_000,
                "currency": "IQD",
            },
        )
        self.assertIsNotNone(issued)
        return issued

    def test_advisory_reads_and_committed_writes_close_without_garbage_collection(
        self,
    ) -> None:
        with patch("sqlite3.connect", side_effect=self.connect):
            self.app.assist = PaymentAssist(self.app.wallet)
            issued = self.prepare()
            self.app.assist.record_decision("demo_amina", issued.draft, "CONFIRMED")
            ledger_snapshot(self.path)
        self.assert_connections_closed()
        with closing(self.original_connect(self.path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM review_context").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[
                    0
                ],
                1,
            )
        # Connections remain strongly referenced above. Cleanup must still work
        # on Windows; relying on CPython garbage collection would fail this.
        self.path.unlink()

    def test_advisory_write_failure_rolls_back_and_closes(self) -> None:
        issued = self.prepare()
        before = ledger_snapshot(self.path)
        self.fail_decision_insert = True
        with (
            patch("sqlite3.connect", side_effect=self.connect),
            self.assertRaisesRegex(RuntimeError, "synthetic failure"),
        ):
            self.app.assist.record_decision("demo_amina", issued.draft, "CONFIRMED")
        self.assert_connections_closed()
        with closing(self.original_connect(self.path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[
                    0
                ],
                0,
            )
        self.assertEqual(before, ledger_snapshot(self.path))

    def test_failed_ledger_snapshot_closes_its_connection(self) -> None:
        empty_path = Path(self.tempdir.name) / "empty.sqlite3"
        with (
            patch("sqlite3.connect", side_effect=self.connect),
            self.assertRaises(sqlite3.OperationalError),
        ):
            ledger_snapshot(empty_path)
        self.assert_connections_closed()
        empty_path.unlink()


if __name__ == "__main__":
    unittest.main()
