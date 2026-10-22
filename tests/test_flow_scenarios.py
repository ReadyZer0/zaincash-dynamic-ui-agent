"""Check workflow oracles catch unsafe behavior, not just happy-path output."""

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import IssuedDraft
from evaluation.flow_scenarios import SCENARIOS, main, run_suite
from server import DemoApp


class UnsafeTypedApprovalApp(DemoApp):
    def chat(self, session, message):
        response, issued = super().chat(session, message)
        if isinstance(issued, IssuedDraft):
            self.saved_review = issued
        if message == "كمل":
            review = self.saved_review
            self.confirm_draft(session, review.draft["id"], review.confirmation_token)
        return response, issued


class WrongRecipientReceiptApp(DemoApp):
    def confirm_draft(self, *args):
        response = super().confirm_draft(*args)
        response["transaction"]["counterparty"] = "مستلم تجريبي خطأ"
        return response


class ExceptionWithSecretApp(DemoApp):
    def chat(self, *_args):
        raise RuntimeError("CANARY-PRIVATE-KEY-MUST-NOT-APPEAR")


class FlowScenarioTests(unittest.TestCase):
    def test_all_ten_workflows_pass_without_model_even_if_environment_requests_one(self):
        with patch.dict(os.environ, {"READY_AGENT_MODE": "llm", "READY_LLM_API_KEY": "CANARY-ENV-KEY"}), \
             patch("llm_agent.AgentRunner.run", side_effect=AssertionError("Model call forbidden")):
            report = run_suite()
        self.assertEqual(report["summary"]["scenarios"], 10)
        self.assertEqual(report["summary"]["passed"], 10, report["results"])
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertFalse(report["uses_live_model"])
        self.assertFalse(report["held_out"])
        self.assertEqual(len({spec["id"] for spec in SCENARIOS}), 10)
        self.assertNotIn("CANARY-ENV-KEY", json.dumps(report))

    def test_typed_approval_mutation_is_detected_even_without_transaction_response(self):
        report = run_suite(["WF003"], app_factory=UnsafeTypedApprovalApp)
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertEqual(report["results"][0]["failure_code"], "chat_keeps_both_owners_ledger_unchanged")

    def test_wrong_recipient_receipt_is_rejected(self):
        report = run_suite(["WF001"], app_factory=WrongRecipientReceiptApp)
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertEqual(report["results"][0]["failure_code"], "confirmed_recipient_matches_review")

    def test_arbitrary_exception_text_is_not_evidence(self):
        report = run_suite(["WF003"], app_factory=ExceptionWithSecretApp)
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertEqual(report["results"][0]["exception_type"], "RuntimeError")
        self.assertNotIn("CANARY-PRIVATE-KEY-MUST-NOT-APPEAR", json.dumps(report))

    def test_cli_writes_honest_report_and_failure_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(StringIO()):
            self.assertEqual(main(["--case", "WF003", "--output-dir", folder]), 0)
            reports = list(Path(folder).glob("*.json"))
            self.assertEqual(len(reports), 1)
            result = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(result["summary"]["scenarios"], 1)
            self.assertIn("No live model", result["claim_boundary"])
            self.assertEqual(len(list(Path(folder).glob("*.md"))), 1)
        failed = run_suite(["WF003"], app_factory=UnsafeTypedApprovalApp)
        with patch("evaluation.flow_scenarios.run_suite", return_value=failed), redirect_stdout(StringIO()):
            self.assertEqual(main(["--case", "WF003"]), 1)

    def test_unknown_or_empty_selection_is_not_reported_as_success(self):
        for selection in ([], ["WF999"], ["WF001", "WF999"]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                run_suite(selection)


if __name__ == "__main__":
    unittest.main()
