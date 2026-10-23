"""Payment-advisory failure isolation, source evidence and support boundaries.

These are direct application tests with fresh synthetic databases. They exercise
the real wallet ledger; no external provider or payment service is contacted.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import WalletError
from llm_agent import LLMConfig
from server import DemoApp


class PaymentAssistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "assist.sqlite3"
        self.app = DemoApp(self.path, agent_config=LLMConfig(mode="offline"))
        self.session = self.app.bootstrap("demo_amina")["session"]

    def prepare(self, amount: int = 80_000):
        _response, issued = self.app.dispatch_action(
            self.session, "OPEN_TRANSFER",
            {"recipient_id": "contact_ali_diaa", "amount_minor": amount, "currency": "IQD"},
        )
        self.assertIsNotNone(issued)
        return issued

    def balance(self) -> int:
        return self.app.wallet.get_balance("demo_amina")["available_minor"]

    def row(self, sql: str, parameters: tuple = ()) -> tuple:
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute(sql, parameters).fetchone()

    def test_audit_failure_after_debit_preserves_receipt_and_retry_idempotence(self) -> None:
        issued = self.prepare()
        before = self.balance()
        with patch.object(self.app.assist, "record_decision", side_effect=sqlite3.OperationalError("audit unavailable")):
            response = self.app.confirm_draft(self.session, issued.draft["id"], issued.confirmation_token)
            retry = self.app.confirm_draft(self.session, issued.draft["id"], issued.confirmation_token)
        self.assertFalse(response["advisory_recorded"])
        self.assertEqual(response["transaction"]["status"], "SUCCEEDED")
        self.assertEqual(response["transaction"]["receipt"]["total_debit_minor"], 80_250)
        self.assertEqual(before - self.balance(), 80_250)
        self.assertEqual(retry["transaction"]["id"], response["transaction"]["id"])
        self.assertTrue(retry["transaction"]["duplicate"])
        self.assertEqual(self.row("SELECT COUNT(*) FROM transactions WHERE draft_id=?", (issued.draft["id"],))[0], 1)
        self.assertNotIn(issued.confirmation_token, json.dumps(response))

    def test_optional_balance_failure_cannot_hide_committed_receipt(self) -> None:
        issued = self.prepare(10_000)
        before = self.balance()
        with patch.object(self.app.wallet, "get_balance", side_effect=sqlite3.OperationalError("balance read unavailable")):
            response = self.app.confirm_draft(self.session, issued.draft["id"], issued.confirmation_token)
        self.assertTrue(response["balance_unavailable"])
        self.assertNotIn("balance", response)
        self.assertEqual(response["transaction"]["status"], "SUCCEEDED")
        self.assertEqual(response["transaction"]["receipt"]["total_debit_minor"], 10_250)
        self.assertEqual(before - self.balance(), 10_250)

    def test_cancellation_records_codes_from_the_reviewed_version(self) -> None:
        issued = self.prepare()
        before = self.balance()
        reviewed_codes = {item["code"] for item in issued.draft["payment_context"]["signals"]}
        self.assertIn("LARGE_SHARE", reviewed_codes)
        response = self.app.cancel_draft(self.session, issued.draft["id"])
        self.assertTrue(response["advisory_recorded"])
        self.assertEqual(response["draft"]["state"], "CANCELLED")
        self.assertEqual(response["draft"]["version"], issued.draft["version"] + 1)
        version, owner, codes = self.row(
            "SELECT version,owner_user_id,risk_codes_json FROM review_decisions WHERE draft_id=? AND decision='CANCELLED'",
            (issued.draft["id"],),
        )
        self.assertEqual(version, issued.draft["version"])
        self.assertEqual(owner, "demo_amina")
        self.assertEqual(set(json.loads(codes)), reviewed_codes)
        self.assertEqual(self.balance(), before)

    def test_existing_fixture_name_is_not_misreported_as_new_recipient(self) -> None:
        issued = self.prepare(10_000)
        self.assertNotIn("NEW_RECIPIENT", {item["code"] for item in issued.draft["payment_context"]["signals"]})
        # A fresh preparation with no successful history does carry that reason.
        with patch.object(self.app.wallet, "get_history", return_value={"items": []}):
            fresh = self.prepare(10_000)
        self.assertIn("NEW_RECIPIENT", {item["code"] for item in fresh.draft["payment_context"]["signals"]})

    def test_audit_failure_cannot_undo_cancellation_or_reenable_old_approval(self) -> None:
        issued = self.prepare()
        before = self.balance()
        with patch.object(self.app.assist, "record_decision", side_effect=sqlite3.OperationalError("audit unavailable")):
            response = self.app.cancel_draft(self.session, issued.draft["id"])
        self.assertFalse(response["advisory_recorded"])
        self.assertEqual(response["draft"]["state"], "CANCELLED")
        with self.assertRaises(WalletError) as raised:
            self.app.confirm_draft(self.session, issued.draft["id"], issued.confirmation_token)
        self.assertEqual(raised.exception.code, "DRAFT_CANCELLED")
        self.assertEqual(self.balance(), before)
        self.assertEqual(self.row("SELECT COUNT(*) FROM transactions WHERE draft_id=?", (issued.draft["id"],))[0], 0)

    def test_unavailable_context_preserves_review_and_completed_status_recovery(self) -> None:
        with patch.object(self.app.assist, "attach_context", side_effect=sqlite3.OperationalError("context unavailable")):
            issued = self.prepare(10_000)
        self.assertTrue(issued.draft["context_unavailable"])
        self.assertTrue(issued.draft["can_confirm"])
        response = self.app.confirm_draft(self.session, issued.draft["id"], issued.confirmation_token)
        after = self.balance()
        with patch.object(self.app.assist, "attach_context", side_effect=ValueError("invalid advisory JSON")):
            recovered = self.app.draft_status(self.session, issued.draft["id"])
        self.assertTrue(recovered["draft"]["context_unavailable"])
        self.assertEqual(recovered["transaction"]["id"], response["transaction"]["id"])
        self.assertEqual(recovered["transaction"]["receipt"], response["transaction"]["receipt"])
        self.assertEqual(recovered["transaction"]["status"], "SUCCEEDED")
        self.assertEqual(self.balance(), after)

    def test_insights_total_is_traceable_and_excludes_other_owners_and_unsettled_rows(self) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE transactions SET status='FAILED',receipt_json=NULL WHERE id='tx_history_amina_002'")
            connection.execute("UPDATE transactions SET status='UNKNOWN',receipt_json=NULL WHERE id='tx_history_amina_003'")
        before = self.balance()
        response, issued = self.app.dispatch_action(self.session, "VIEW_WALLET_INSIGHTS", {})
        data = response["view"]["data"]
        self.assertIsNone(issued)
        self.assertEqual(data["successful_total_minor"], 12_500)
        self.assertEqual(data["unknown_count"], 1)
        self.assertEqual(data["failed_count"], 1)
        self.assertEqual(data["available_minor"], 150_000)
        self.assertEqual({row["id"] for row in data["source_records"]},
                         {"tx_history_amina_001", "tx_history_amina_002", "tx_history_amina_003"})
        for record in data["source_records"]:
            owner, reference, amount, status = self.row(
                "SELECT owner_user_id,reference,debit_minor,status FROM transactions WHERE id=?", (record["id"],)
            )
            self.assertEqual(owner, "demo_amina")
            self.assertEqual((record["reference"], record["amount_minor"], record["status"]), (reference, amount, status))
        hassan = self.app.assist.wallet_insights("demo_hassan")
        self.assertEqual(hassan["successful_total_minor"], 37_500)
        self.assertTrue({row["id"] for row in data["source_records"]}.isdisjoint(row["id"] for row in hassan["source_records"]))
        self.assertEqual(self.balance(), before)

    def test_support_packet_uses_original_record_and_does_not_send_or_debit(self) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE transactions SET status='UNKNOWN',receipt_json=NULL WHERE id='tx_history_amina_003'")
        before = self.balance()
        before_count = self.row("SELECT COUNT(*) FROM transactions")[0]
        with patch("socket.create_connection", side_effect=AssertionError("support must not contact an external service")):
            response, issued = self.app.dispatch_action(self.session, "PREPARE_SUPPORT_REQUEST", {
                "transaction_id": "MOCK-HIST-AMINA-003", "issue": "الفاتورة بعدها ما ظهرت مدفوعة عند الجهة",
            })
        packet = response["view"]["data"]
        self.assertIsNone(issued)
        self.assertFalse(packet["sent"])
        self.assertEqual(packet["transaction_id"], "tx_history_amina_003")
        self.assertEqual(packet["recorded_status"], "UNKNOWN")
        self.assertIn("MOCK-HIST-AMINA-003", packet["draft_text"])
        self.assertIn("45,000 IQD", packet["draft_text"])
        self.assertIn("غير متحقق", packet["draft_text"])
        self.assertIn("لا تعيد الدفع", packet["next_step"])
        self.assertEqual(self.balance(), before)
        self.assertEqual(self.row("SELECT COUNT(*) FROM transactions")[0], before_count)

    def test_support_rejects_foreign_records_and_secrets(self) -> None:
        for identifier in ("tx_history_hassan_001", "MOCK-HIST-HASSAN-001"):
            with self.subTest(foreign_record=identifier), self.assertRaises(WalletError) as raised:
                self.app.assist.support_draft("demo_amina", identifier, "أحتاج أتأكد من النتيجة")
            self.assertEqual(raised.exception.code, "TRANSACTION_NOT_FOUND")
        for issue in ("OTP 123456", "PIN 1234", "api_key fixture-secret", "Bearer session-secret", "رمز الدخول 12345"):
            with self.subTest(secret=issue), self.assertRaises(WalletError) as raised:
                self.app.assist.support_draft("demo_amina", "MOCK-HIST-AMINA-001", issue)
            self.assertEqual(raised.exception.code, "SECRET_IN_SUPPORT")
            self.assertNotIn(issue, raised.exception.message)


if __name__ == "__main__":
    unittest.main()
