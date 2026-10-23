"""Checks that evaluation reports mistakes instead of manufacturing a score."""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from evaluation.run import compare, evaluate_case, load_cases, main, observe, summarize
from llm_agent import LLMConfig
from server import DemoApp


class EvaluationTests(unittest.TestCase):
    def test_dataset_has_distinct_cases_and_honest_review_status(self) -> None:
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 60)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertTrue(any(len(case["turns"]) > 1 for case in cases))
        metadata_path = Path(__file__).resolve().parents[1] / "evaluation" / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertFalse(metadata["held_out"])
        self.assertFalse(metadata["human_reviewed"])

    def test_wrong_recipient_amount_and_fee_fail_even_before_any_debit(self) -> None:
        expected = {"outcome": "draft", "draft_kind": "transfer", "amount_minor": 50_000,
                    "recipient_or_biller": "علي ضياء", "currency": "IQD",
                    "total_debit_minor": 50_250}
        observed = {**expected, "recipient_or_biller": "علي محمد", "amount_minor": 5_000,
                    "total_debit_minor": 5_000}
        failures = compare(expected, observed)
        self.assertEqual(len(failures), 3)
        self.assertTrue(any("recipient_or_biller" in failure for failure in failures))

    def test_forbidden_proposal_and_provider_failure_are_not_safe_successes(self) -> None:
        expected = {"outcome": "safe_reply", "forbid_draft": True}
        self.assertTrue(compare(expected, {"outcome": "draft"}))
        self.assertTrue(compare(expected, {"outcome": "error", "error_code": "MODEL_TIMEOUT"}))
        self.assertTrue(compare(expected, {"outcome": "error", "error_code": "UNSAFE_TOOL_RESULT"}))
        self.assertTrue(compare(expected, {"outcome": "error", "error_code": "AUTH_REQUIRED"}))
        self.assertTrue(compare(expected, {"outcome": "error", "error_code": "UNEXPECTED_NEW_CODE"}))
        self.assertTrue(compare(expected, observe({"clarification": {"field": "request", "prompt": ""}})))
        self.assertTrue(compare(expected, observe({})))
        self.assertFalse(compare(expected, observe({"messages": [{"text": "راجع الطلب أولاً."}]})))
        self.assertFalse(compare(expected, {"outcome": "error", "error_code": "AMOUNT_LIMIT"}))

    def test_wrong_insight_totals_and_support_sent_status_fail(self) -> None:
        expected = {"outcome": "view", "view_kind": "wallet_insights",
                    "view_facts": {"available_minor": 150_000, "successful_total_minor": 82_500}}
        observed = observe({"view": {"kind": "wallet_insights", "data": {
            "available_minor": 150_000, "successful_total_minor": 999_999
        }}})
        self.assertTrue(compare(expected, observed))
        expected_support = {"outcome": "view", "view_kind": "support_form", "view_facts": {"sent": False}}
        self.assertTrue(compare(expected_support, observe({"view": {"kind": "support_form", "data": {"sent": True}}})))

    def test_observation_discards_free_text_and_unrelated_response_secrets(self) -> None:
        secret = "fake-test-only-secret"
        observed = observe({
            "messages": [{"role": "assistant", "text": secret}],
            "session": {"id": secret, "csrf_token": secret},
            "agent": {"raw_provider_response": secret},
            "view": {"kind": "balance", "data": {"available_minor": 150_000}},
        })
        self.assertNotIn(secret, json.dumps(observed))
        self.assertEqual(observed["view_kind"], "balance")

    def test_explicit_offline_run_ignores_live_environment(self) -> None:
        case = load_cases()[0]
        with patch.dict("os.environ", {"READY_AGENT_MODE": "llm", "READY_LLM_API_KEY": "fake-key"}):
            with patch("llm_agent.OpenAICompatibleClient.complete", side_effect=AssertionError("Network must not run")):
                result = evaluate_case(case, LLMConfig(mode="offline"))
        self.assertTrue(result["passed"], result)
        self.assertFalse(any(turn["ledger_changed"] for turn in result["turns"]))

    def test_ledger_check_detects_changes_to_a_different_demo_owner(self) -> None:
        class MutatingApp(DemoApp):
            def __init__(self, database_path, **kwargs):
                super().__init__(database_path, **kwargs)
                self.test_database_path = database_path

            def chat(self, session, message):
                response = super().chat(session, message)
                with closing(sqlite3.connect(self.test_database_path)) as connection, connection:
                    connection.execute(
                        "UPDATE accounts SET available_minor = available_minor - 1 WHERE user_id = 'demo_hassan'"
                    )
                return response

        result = evaluate_case(load_cases()[0], LLMConfig(mode="offline"), app_factory=MutatingApp)
        self.assertFalse(result["passed"])
        self.assertTrue(result["turns"][0]["ledger_changed"])

    def test_multiturn_case_is_failed_if_any_step_is_wrong(self) -> None:
        results = [{"category": "multiturn", "passed": False, "turns": [
            {"passed": True, "ledger_changed": False, "duration_ms": 2.0,
             "observed": {"outcome": "clarification"}},
            {"passed": False, "ledger_changed": False, "duration_ms": 4.0,
             "observed": {"outcome": "draft"}},
        ]}]
        summary = summarize(results)
        self.assertEqual(summary["passed_cases"], 0)
        self.assertEqual(summary["passed_turns"], 1)
        self.assertEqual(summary["incorrect_payment_proposals"], 1)
        self.assertEqual(summary["latency_ms"]["p95"], 4.0)

    def test_duplicate_case_ids_and_unlabelled_drafts_are_rejected(self) -> None:
        case = load_cases()[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            path.write_text(json.dumps(case) + "\n" + json.dumps(case), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_cases(path)
            case["turns"][0]["expected"] = {"outcome": "draft"}
            path.write_text(json.dumps(case), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "draft label"):
                load_cases(path)

    def test_live_cli_requires_explicit_network_flag(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            main(["--mode", "llm"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("--allow-network", stderr.getvalue())

    def test_failed_live_run_reports_reserved_attempts_without_exposing_key(self) -> None:
        config = LLMConfig(mode="llm", base_url="https://example.test/v1",
                           model="synthetic-test-model", api_key="unit-test-only-key", request_cap=5)

        def failed_case(_case, run_config):
            self.assertTrue(run_config._request_budget.reserve())
            self.assertTrue(run_config._request_budget.reserve())
            return {"id": "R001", "category": "balance", "passed": False, "turns": [{
                "turn": 1, "message": "synthetic test", "passed": False,
                "ledger_changed": False, "duration_ms": 1.0,
                "observed": {"outcome": "error", "error_code": "MODEL_TIMEOUT"},
                "failures": ["provider timed out"],
            }]}

        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "attempts"
            with patch.object(LLMConfig, "from_env", return_value=config), \
                    patch("evaluation.run.evaluate_case", side_effect=failed_case), \
                    redirect_stdout(io.StringIO()):
                result = main(["--mode", "llm", "--allow-network", "--limit", "1",
                               "--output", str(prefix)])
            report_text = prefix.with_suffix(".json").read_text(encoding="utf-8")
            report = json.loads(report_text)
            self.assertEqual(result, 1)
            self.assertEqual(report["provider_usage"]["reserved_attempts"], 2)
            self.assertEqual(report["provider_usage"]["process_cap"], 5)
            self.assertNotIn(config.api_key, report_text)
            self.assertIn("2 / 5", prefix.with_suffix(".md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
