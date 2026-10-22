"""Deterministic Iraqi-Arabic mock API workflow scenarios.

Run ``python -m evaluation.flow_scenarios --output-dir evaluation/results``.
Each journey gets a fresh SQLite database and explicitly selects the rule-based
test router. Calls use DemoApp's trusted API-handler boundary directly. They do
not drive a browser, issue HTTP requests, call an LLM, or send real payments.
Consequently these results do not measure dialect quality, Gemini behavior,
HTTP/CSRF/cookie protection, Android usability, or production integration.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
from typing import Any, Callable

from core import IssuedDraft, WalletError
from llm_agent import LLMConfig
from server import DemoApp


ROOT = Path(__file__).resolve().parents[1]
CLAIM_BOUNDARY = (
    "Deterministic mock API-handler workflows with separate trusted Confirm "
    "calls. No live model, browser, HTTP/CSRF/cookie, Android, or real-payment "
    "validation is claimed. Iraqi-Arabic inputs are AI-authored development "
    "fixtures, not a human-reviewed or held-out dialect evaluation."
)


def _spec(case_id: str, title: str, kind: str, messages: list[str], *,
          amina: int = 150_000, hassan: int = 87_500, new_transactions: int = 0,
          errors: tuple[str, ...] = (), user_id: str = "demo_amina") -> dict[str, Any]:
    return {
        "id": case_id, "title_ar_iq": title, "kind": kind,
        "user_id": user_id, "chat_messages": messages,
        "expected_final": {
            "balances": {"demo_amina": amina, "demo_hassan": hassan},
            "new_transactions": new_transactions,
            "new_successful_transactions": new_transactions,
        },
        "expected_error_codes": list(errors),
    }


# Oracles are fixed from the synthetic fixture and lifecycle contract before
# execution. The 250-IQD transfer fee is a mock fee, not ZainCash pricing.
SCENARIOS = (
    _spec("WF001", "اختيار علي الصحيح ثم تأكيد التحويل", "clarified_transfer",
          ["حول ٥٠ ألف لعلي", "علي ضياء"], amina=99_750, new_transactions=1),
    _spec("WF002", "فاتورة حسن ومراجعتها وتأكيدها", "saved_bill",
          ["فاتورة الموبايل أريد أدفعها"], hassan=69_500,
          new_transactions=1, user_id="demo_hassan"),
    _spec("WF003", "كلمة كمل ما تنفذ التحويل", "typed_approval",
          ["حول ١٠ آلاف لعلي ضياء", "كمل"]),
    _spec("WF004", "الإلغاء يبطل التأكيد القديم", "cancelled_review",
          ["حول ١٠ آلاف لعلي ضياء"], errors=("DRAFT_CANCELLED",)),
    _spec("WF005", "تغيير المبلغ يحتاج مراجعة وتأكيد جديد", "edited_review",
          ["حول ١٠ آلاف لعلي ضياء", "غير المبلغ خلي ٢٥ ألف"],
          amina=124_750, new_transactions=1, errors=("STALE_CONFIRMATION",)),
    _spec("WF006", "ضغط التأكيد مرتين يخصم مرة واحدة", "duplicate_confirm",
          ["حول ١٠ آلاف لعلي ضياء"], amina=139_750, new_transactions=1),
    _spec("WF007", "انقطاع الرد واسترجاع نفس نتيجة التحويل", "unknown_recovery",
          ["حول ٢٠ ألف لعلي محمد"], amina=129_750, new_transactions=1),
    _spec("WF008", "الرصيد ما يكفي ويا الأجور", "insufficient_balance",
          ["حول ١٥٠ ألف لعلي ضياء"], errors=("INSUFFICIENT_BALANCE",)),
    _spec("WF009", "حساب حسن ما يؤكد مراجعة أمينة", "other_owner",
          ["حول ١٠ آلاف لعلي ضياء"], errors=("DRAFT_NOT_FOUND",)),
    _spec("WF010", "انتهاء صلاحية المراجعة يمنع الخصم", "expired_review",
          ["حول ١٠ آلاف لعلي ضياء"], errors=("DRAFT_EXPIRED",)),
)


class ScenarioFailure(Exception):
    """Contains an assertion label only, never a token or provider payload."""


def ledger_snapshot(path: Path) -> dict[str, Any]:
    with sqlite3.connect(path) as connection:
        balances = dict(connection.execute(
            "SELECT user_id, available_minor FROM accounts ORDER BY user_id"
        ).fetchall())
        transactions = connection.execute(
            "SELECT id, owner_user_id, status, debit_minor, draft_id "
            "FROM transactions ORDER BY id"
        ).fetchall()
    return {"balances": balances, "transactions": transactions}


def _public_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Allowlisted facts only; do not serialize arbitrary response bodies."""
    summary: dict[str, Any] = {}
    if isinstance(payload.get("clarification"), dict):
        summary["clarification_field"] = payload["clarification"].get("field")
        summary["choice_ids"] = [
            row.get("id") for row in payload["clarification"].get("choices", [])
            if isinstance(row, dict)
        ]
    if isinstance(payload.get("draft"), dict):
        draft = payload["draft"]
        summary["draft"] = {key: draft.get(key) for key in
                            ("id", "kind", "state", "version", "can_confirm")}
        review = draft.get("review", {})
        summary["review"] = {key: review.get(key) for key in (
            "recipient_or_biller", "amount_minor", "currency", "fee_minor",
            "total_debit_minor",
        )}
    if isinstance(payload.get("transaction"), dict):
        transaction = payload["transaction"]
        summary["transaction"] = {key: transaction.get(key) for key in (
            "id", "reference", "status", "debit_minor", "counterparty",
            "currency", "duplicate",
        )}
        summary["has_receipt"] = isinstance(transaction.get("receipt"), dict)
    if isinstance(payload.get("balance"), dict):
        summary["available_minor"] = payload["balance"].get("available_minor")
    return summary


class Journey:
    def __init__(self, spec: dict[str, Any], path: Path,
                 app_factory: Callable[..., DemoApp]) -> None:
        self.spec = spec
        self.path = path
        # Never inherit a live provider configuration from the environment.
        self.app = app_factory(path, agent_config=LLMConfig(mode="offline"))
        self.session = self.app.bootstrap(spec["user_id"])["session"]
        self.initial = ledger_snapshot(path)
        self.events: list[dict[str, Any]] = []
        self.assertions: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self._private_values = [self.session["id"], self.session["csrf_token"]]

    def check(self, condition: bool, label: str) -> None:
        self.assertions.append({"label": label, "passed": bool(condition)})
        if not condition:
            raise ScenarioFailure(label)

    def _public_response(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False)
        self.check("confirmation_token" not in encoded, "no_confirmation_token_in_public_response")
        self.check(not any(value and value in encoded for value in self._private_values),
                   "no_session_or_confirmation_credentials_in_public_response")

    def chat(self, message: str) -> tuple[dict[str, Any], IssuedDraft | None]:
        before = ledger_snapshot(self.path)
        start = time.monotonic()
        response, issued = self.app.chat(self.session, message)
        if isinstance(issued, IssuedDraft):
            self._private_values.append(issued.confirmation_token)
        self._public_response(response)
        self.events.append({
            "event": "chat", "message_ar_iq": message,
            "duration_ms": round((time.monotonic() - start) * 1000, 2),
            "observed": _public_summary(response),
        })
        self.check(response.get("transaction") is None, "chat_never_returns_completed_transaction")
        self.check(ledger_snapshot(self.path) == before, "chat_keeps_both_owners_ledger_unchanged")
        return response, issued

    def prepare(self, message: str, amount: int, recipient: str = "علي ضياء",
                *, bill: bool = False) -> IssuedDraft:
        response, issued = self.chat(message)
        self.check(isinstance(issued, IssuedDraft), "issued_payment_review")
        assert isinstance(issued, IssuedDraft)
        review = response.get("draft", {}).get("review", {})
        expected = {
            "recipient_or_biller": recipient, "amount_minor": amount,
            "currency": "IQD", "fee_minor": 0 if bill else 250,
            "total_debit_minor": amount + (0 if bill else 250),
        }
        for key, value in expected.items():
            self.check(review.get(key) == value, "review_exact_" + key)
        self.check(response["draft"].get("kind") == ("bill_payment" if bill else "transfer"),
                   "review_exact_kind")
        self.check(response["draft"].get("can_confirm") is True, "review_offers_separate_confirm")
        return issued

    def confirm(self, issued: IssuedDraft) -> dict[str, Any]:
        start = time.monotonic()
        # This is the separate trusted UI/API-handler call. The token never
        # appears in user text, model messages, public observations or reports.
        response = self.app.confirm_draft(
            self.session, issued.draft["id"], issued.confirmation_token
        )
        self._public_response(response)
        self.events.append({
            "event": "trusted_confirm_handler", "draft_id": issued.draft["id"],
            "duration_ms": round((time.monotonic() - start) * 1000, 2),
            "observed": _public_summary(response),
        })
        transaction = response.get("transaction", {})
        review = issued.draft["review"]
        self.check(transaction.get("status") == "SUCCEEDED", "confirmed_transaction_succeeded")
        self.check(transaction.get("counterparty") == review["recipient_or_biller"],
                   "confirmed_recipient_matches_review")
        self.check(transaction.get("debit_minor") == review["total_debit_minor"],
                   "confirmed_debit_matches_review")
        self.check(transaction.get("currency") == "IQD", "confirmed_currency_iqd")
        receipt = transaction.get("receipt", {})
        self.check(isinstance(receipt, dict) and receipt.get("transaction_id") == transaction.get("id"),
                   "receipt_identifies_original_transaction")
        self.check(receipt.get("reference") == transaction.get("reference"),
                   "receipt_reference_matches_transaction")
        self.check(receipt.get("total_debit_minor") == review["total_debit_minor"],
                   "receipt_debit_matches_review")
        return response

    def rejected(self, event: str, code: str, operation: Callable[[], Any]) -> None:
        before = ledger_snapshot(self.path)
        start = time.monotonic()
        caught = None
        try:
            operation()
        except WalletError as error:
            caught = error.code
        self.events.append({
            "event": event, "error_code": caught,
            "duration_ms": round((time.monotonic() - start) * 1000, 2),
        })
        self.check(caught == code, event + "_exact_error_code")
        self.errors.append(code)
        self.check(ledger_snapshot(self.path) == before, event + "_keeps_ledger_unchanged")

    def execute(self) -> None:
        messages, kind = self.spec["chat_messages"], self.spec["kind"]
        if kind == "clarified_transfer":
            response, issued = self.chat(messages[0])
            self.check(issued is None and "draft" not in response, "ambiguous_recipient_has_no_draft")
            clarification = response.get("clarification", {})
            self.check(clarification.get("field") == "recipient", "asks_which_ali")
            self.check({row["id"] for row in clarification.get("choices", [])} ==
                       {"contact_ali_diaa", "contact_ali_mohammed"}, "offers_only_current_owner_ali_choices")
            self.confirm(self.prepare(messages[1], 50_000))
        elif kind == "saved_bill":
            self.confirm(self.prepare(messages[0], 18_000, "فاتورة موبايل تجريبية", bill=True))
        else:
            amount = 20_000 if kind == "unknown_recovery" else 150_000 if kind == "insufficient_balance" else 10_000
            recipient = "علي محمد" if kind == "unknown_recovery" else "علي ضياء"
            issued = self.prepare(messages[0], amount, recipient)
            draft_id, token = issued.draft["id"], issued.confirmation_token
            if kind == "typed_approval":
                response, next_issued = self.chat(messages[1])
                self.check(next_issued is None and "draft" not in response,
                           "typed_approval_does_not_issue_a_new_review")
            elif kind == "cancelled_review":
                cancelled = self.app.cancel_draft(self.session, draft_id)
                self.events.append({"event": "trusted_cancel_handler", "observed": _public_summary(cancelled)})
                self.check(cancelled["draft"]["state"] == "CANCELLED", "review_cancelled")
                self.rejected("confirm_cancelled", "DRAFT_CANCELLED",
                              lambda: self.app.confirm_draft(self.session, draft_id, token))
            elif kind == "edited_review":
                updated = self.prepare(messages[1], 25_000)
                self.check(updated.draft["id"] == draft_id, "edited_review_retains_id")
                self.check(updated.draft["version"] > issued.draft["version"], "edited_review_advances_version")
                self.rejected("confirm_old_version", "STALE_CONFIRMATION",
                              lambda: self.app.confirm_draft(self.session, draft_id, token))
                self.confirm(updated)
            elif kind == "duplicate_confirm":
                original = self.confirm(issued)
                repeated = self.confirm(issued)
                self.check(original["transaction"]["id"] == repeated["transaction"]["id"],
                           "repeated_confirm_returns_same_transaction")
                self.check(repeated["transaction"]["duplicate"] is True, "repeat_identified_as_duplicate")
            elif kind == "unknown_recovery":
                original = self.confirm(issued)
                transaction_id = original["transaction"]["id"]
                # Existing local fault fixture: result was durably recorded,
                # but the client/provider-facing state becomes UNKNOWN.
                self.app.wallet._mark_transaction_unknown_for_test(transaction_id)
                self.events.append({"event": "inject_unknown_after_durable_mock_result",
                                    "transaction_id": transaction_id})
                with sqlite3.connect(self.path) as connection:
                    status = connection.execute("SELECT status FROM transactions WHERE id = ?", (transaction_id,)).fetchone()[0]
                self.check(status == "UNKNOWN", "fault_fixture_really_became_unknown")
                start = time.monotonic()
                recovered = self.app.draft_status(self.session, draft_id)
                self._public_response(recovered)
                self.events.append({"event": "trusted_status_handler",
                                    "duration_ms": round((time.monotonic() - start) * 1000, 2),
                                    "observed": _public_summary(recovered)})
                self.check(recovered["transaction"]["id"] == transaction_id, "recovery_uses_original_transaction")
                self.check(recovered["transaction"]["status"] == "SUCCEEDED", "recovery_reads_durable_mock_result")
                self.check(recovered["transaction"]["receipt"] == original["transaction"]["receipt"],
                           "recovery_restores_original_receipt")
            elif kind == "insufficient_balance":
                self.rejected("confirm_insufficient_balance", "INSUFFICIENT_BALANCE",
                              lambda: self.app.confirm_draft(self.session, draft_id, token))
            elif kind == "other_owner":
                other = self.app.bootstrap("demo_hassan")["session"]
                self._private_values.extend([other["id"], other["csrf_token"]])
                self.rejected("other_owner_confirm", "DRAFT_NOT_FOUND",
                              lambda: self.app.confirm_draft(other, draft_id, token))
            elif kind == "expired_review":
                self.app.wallet._expire_draft_for_test(draft_id)
                self.events.append({"event": "advance_review_expiry_fixture", "draft_id": draft_id})
                self.rejected("confirm_expired", "DRAFT_EXPIRED",
                              lambda: self.app.confirm_draft(self.session, draft_id, token))
                self.check(self.app.draft_status(self.session, draft_id)["draft"]["state"] == "EXPIRED",
                           "status_shows_expired_review")
            else:
                raise ScenarioFailure("unknown_scenario_kind")
        self.verify_final()

    def final_facts(self) -> dict[str, Any]:
        current = ledger_snapshot(self.path)
        old_ids = {row[0] for row in self.initial["transactions"]}
        new_rows = [row for row in current["transactions"] if row[0] not in old_ids]
        return {
            "balances": current["balances"], "new_transactions": len(new_rows),
            "new_successful_transactions": sum(row[2] == "SUCCEEDED" for row in new_rows),
            "new_transaction_ids": [row[0] for row in new_rows],
        }

    def verify_final(self) -> None:
        facts = self.final_facts()
        for key, expected in self.spec["expected_final"].items():
            self.check(facts[key] == expected, "final_exact_" + key)
        self.check(self.errors == self.spec["expected_error_codes"], "expected_domain_rejections_observed")
        current = ledger_snapshot(self.path)
        old_by_id = {row[0]: row for row in self.initial["transactions"]}
        self.check(all(row == old_by_id[row[0]] for row in current["transactions"] if row[0] in old_by_id)
                   and old_by_id.keys() <= {row[0] for row in current["transactions"]},
                   "seeded_history_rows_preserved")


def _source_metadata() -> dict[str, Any]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, check=True, timeout=3).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                                    text=True, check=True, timeout=3).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    digest = hashlib.sha256()
    for relative in ("agent.py", "core.py", "server.py", "action_registry.py", "payment_assist.py",
                     "llm_agent.py", "evaluation/flow_scenarios.py"):
        digest.update(relative.encode())
        digest.update((ROOT / relative).read_bytes())
    return {"commit": commit, "working_tree_dirty": dirty,
            "source_fingerprint_sha256": digest.hexdigest()}


def run_suite(case_ids: list[str] | None = None, *,
              app_factory: Callable[..., DemoApp] = DemoApp) -> dict[str, Any]:
    selected = list(SCENARIOS) if case_ids is None else [spec for spec in SCENARIOS if spec["id"] in case_ids]
    known = {spec["id"] for spec in SCENARIOS}
    if not selected or (case_ids is not None and set(case_ids) - known):
        raise ValueError("Select at least one known workflow scenario ID")
    results = []
    for spec in selected:
        started = time.monotonic()
        result: dict[str, Any] = {"id": spec["id"], "title_ar_iq": spec["title_ar_iq"],
                                  "expected_final": spec["expected_final"], "passed": False}
        with tempfile.TemporaryDirectory(prefix="ready-flow-") as folder:
            journey = None
            try:
                journey = Journey(spec, Path(folder) / "synthetic.sqlite3", app_factory)
                journey.execute()
                result["passed"] = True
            except ScenarioFailure as failure:
                result["failure_code"] = str(failure)
            except Exception as error:
                # Never leak exception messages, request headers or tokens.
                result["failure_code"] = "unexpected_exception"
                result["exception_type"] = type(error).__name__
                if isinstance(error, WalletError):
                    result["domain_error_code"] = error.code
            if journey is not None:
                result.update({"events": journey.events, "assertions": journey.assertions})
                try:
                    result["observed_final"] = journey.final_facts()
                except Exception:
                    result["final_snapshot_unavailable"] = True
        result["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
        results.append(result)
    passed = sum(result["passed"] for result in results)
    return {
        "schema_version": "ready-mock-api-workflows-v1",
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_type": "deterministic_mock_api_workflows",
        "agent_mode": "offline", "uses_live_model": False,
        "human_reviewed": False, "held_out": False,
        "claim_boundary": CLAIM_BOUNDARY, "source": _source_metadata(),
        "summary": {"scenarios": len(results), "passed": passed,
                    "failed": len(results) - passed,
                    "assertions": sum(len(row.get("assertions", [])) for row in results)},
        "results": results,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# Mock API workflow scenario results", "", report["claim_boundary"], "",
             f"Run (UTC): {report['run_at_utc']}", "",
             f"Passed: {report['summary']['passed']}/{report['summary']['scenarios']}", "",
             "| Scenario | Iraqi-Arabic journey | Result | Duration (ms) |",
             "|---|---|---|---:|"]
    for result in report["results"]:
        outcome = "PASS" if result["passed"] else "FAIL: " + result.get("failure_code", "unknown")
        lines.append(f"| {result['id']} | {result['title_ar_iq']} | {outcome} | {result['duration_ms']} |")
    lines.extend(["", "The JSON companion includes each declared final-state oracle, actual event facts, "
                  "assertions and transaction IDs. Session and confirmation credentials are excluded.", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", choices=[row["id"] for row in SCENARIOS],
                        help="Run one scenario; repeat for several. Default: all ten.")
    parser.add_argument("--output-dir", type=Path, help="Write timestamped JSON and Markdown evidence.")
    args = parser.parse_args(argv)
    report = run_suite(args.case)
    paths = []
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        stem = "mock_api_flows_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        for suffix, content in ((".json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
                                (".md", markdown_report(report))):
            target = args.output_dir / (stem + suffix)
            with target.open("x", encoding="utf-8") as stream:
                stream.write(content)
            paths.append(str(target.resolve()))
    print(json.dumps({"summary": report["summary"], "claim_boundary": CLAIM_BOUNDARY,
                      "reports": paths}, ensure_ascii=False))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
