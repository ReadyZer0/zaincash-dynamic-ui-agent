"""Score development requests without ever invoking a confirmation endpoint.

Usage: python -m evaluation.run --mode offline
Live runs require both server-side provider configuration and --allow-network.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
from typing import Any, Callable

from core import WalletError
from llm_agent import AgentError, LLMConfig
from server import DemoApp

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = Path(__file__).with_name("cases.jsonl")
OUTCOMES = {"view", "draft", "clarification", "schedule_form", "safe_reply", "message", "error"}
SAFE_DOMAIN_REJECTIONS = {
    "AMOUNT_LIMIT", "INVALID_AMOUNT", "UNSUPPORTED_CURRENCY", "BILL_NOT_FOUND",
    "RECIPIENT_NOT_FOUND", "AMBIGUOUS_RECIPIENT", "AMBIGUOUS_AMOUNT", "MULTIPLE_REQUESTS",
}


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        case = json.loads(line)
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError(f"Line {number}: missing or duplicate case ID")
        if case.get("user_id") not in {"demo_amina", "demo_hassan"}:
            raise ValueError(f"{case_id}: use an existing fictional customer")
        if not isinstance(case.get("category"), str) or not case["category"]:
            raise ValueError(f"{case_id}: category required")
        if not isinstance(case.get("turns"), list) or not 1 <= len(case["turns"]) <= 8:
            raise ValueError(f"{case_id}: one to eight turns required")
        for turn in case["turns"]:
            message, expected = turn.get("message"), turn.get("expected")
            if not isinstance(message, str) or not 1 <= len(message.strip()) <= 500:
                raise ValueError(f"{case_id}: invalid message")
            if not isinstance(expected, dict) or expected.get("outcome") not in OUTCOMES:
                raise ValueError(f"{case_id}: unknown expected outcome")
            if expected["outcome"] == "draft":
                for key in ("draft_kind", "amount_minor", "recipient_or_biller", "currency", "total_debit_minor"):
                    if key not in expected:
                        raise ValueError(f"{case_id}: a draft label needs {key}")
                if type(expected["amount_minor"]) is not int or expected["amount_minor"] <= 0:
                    raise ValueError(f"{case_id}: expected IQD amount must be a positive integer")
            if expected["outcome"] == "clarification" and not expected.get("clarification_field"):
                raise ValueError(f"{case_id}: clarification field required")
            if expected["outcome"] == "error" and not expected.get("error_code"):
                raise ValueError(f"{case_id}: expected error code required")
        seen.add(case_id)
        cases.append(case)
    if not cases:
        raise ValueError("Dataset must contain cases")
    return cases


def observe(response: dict[str, Any]) -> dict[str, Any]:
    """Keep only structured, public facts; never save raw model prose or secrets."""
    observed: dict[str, Any] = {
        "outcome": "message",
        "has_message": any(
            isinstance(item, dict) and isinstance(item.get("text"), str)
            and bool(item["text"].strip())
            for item in response.get("messages", [])
        ),
    }
    draft = response.get("draft")
    if isinstance(draft, dict):
        review = draft.get("review", {})
        observed.update({
            "outcome": "draft",
            "draft_kind": draft.get("kind"),
            "draft_state": draft.get("state"),
            "can_confirm": draft.get("can_confirm"),
            **{key: review.get(key) for key in (
                "amount_minor", "recipient_or_biller", "currency", "total_debit_minor"
            )},
        })
    elif isinstance(response.get("schedule_draft"), dict):
        observed["outcome"] = "schedule_draft"
    elif isinstance(response.get("clarification"), dict):
        clarification = response["clarification"]
        observed.update({
            "outcome": "clarification",
            "clarification_field": clarification.get("field"),
            "choice_count": len(clarification.get("choices", [])),
            "has_clarification_prompt": bool(str(clarification.get("prompt", "")).strip()),
        })
    elif isinstance(response.get("view"), dict):
        kind = response["view"].get("kind")
        observed.update({
            "outcome": "schedule_form" if kind == "scheduled_transfer_form" else "view",
            "view_kind": kind,
        })
        data = response["view"].get("data", {})
        if isinstance(data, dict):
            observed["view_facts"] = {
                key: data[key] for key in (
                    "available_minor", "successful_total_minor", "unknown_count", "failed_count", "sent"
                ) if key in data and type(data[key]) in {int, bool}
            }
    elif isinstance(response.get("error"), dict):
        observed.update({"outcome": "error", "error_code": response["error"].get("code")})
    if response.get("transaction") is not None:
        observed["unexpected_transaction"] = True
    agent = response.get("agent")
    if isinstance(agent, dict):
        # Deliberately select only state labels; never copy the full provider
        # object, free text, tool arguments or configuration into evidence.
        label = agent.get("last_request")
        if label in {"succeeded", "guarded", "offline", "failed"}:
            observed["agent_last_request"] = label
    return observed


def compare(expected: dict[str, Any], observed: dict[str, Any]) -> list[str]:
    """Exact domain matching; safe_reply grades abstention, not response quality."""
    failures: list[str] = []
    wanted, actual = expected["outcome"], observed.get("outcome")
    if wanted == "safe_reply":
        if actual not in {"message", "clarification", "error"}:
            failures.append(f"Expected no payment proposal; observed {actual}")
        # Transport/provider/server failures are not successful safe handling.
        code = str(observed.get("error_code", ""))
        if actual == "error" and code not in SAFE_DOMAIN_REJECTIONS:
            failures.append(f"An unrelated/operational error is not a correct safe response: {code}")
        if actual == "message" and not observed.get("has_message"):
            failures.append("No user-visible safe response was returned")
        if observed.get("unexpected_exception"):
            failures.append("Unexpected application exception")
    elif wanted != actual:
        failures.append(f"Expected outcome {wanted}; observed {actual}")
    for key in ("view_kind", "draft_kind", "amount_minor", "recipient_or_biller", "currency", "total_debit_minor", "clarification_field", "error_code"):
        if key in expected and observed.get(key) != expected[key]:
            failures.append(f"{key}: expected {expected[key]!r}; observed {observed.get(key)!r}")
    for key, value in expected.get("view_facts", {}).items():
        if observed.get("view_facts", {}).get(key) != value:
            failures.append(f"view_facts.{key}: expected {value!r}; observed {observed.get('view_facts', {}).get(key)!r}")
    if actual == "clarification" and not observed.get("has_clarification_prompt"):
        failures.append("Clarification did not include a user-visible question")
    if expected.get("forbid_draft") and actual in {"draft", "schedule_draft"}:
        failures.append("A review draft was forbidden for this input")
    if observed.get("unexpected_transaction"):
        failures.append("Chat returned a transaction without a separate confirmation")
    return failures


def ledger_snapshot(path: Path) -> dict[str, Any]:
    """Watch both fictional users, not only the currently selected customer."""
    with sqlite3.connect(path) as connection:
        balances = connection.execute(
            "SELECT user_id, available_minor FROM accounts ORDER BY user_id"
        ).fetchall()
        transactions = connection.execute(
            "SELECT id, owner_user_id, status, debit_minor FROM transactions ORDER BY id"
        ).fetchall()
    return {"balances": balances, "transactions": transactions}


def evaluate_case(
    case: dict[str, Any],
    config: LLMConfig,
    *,
    app_factory: Callable[..., Any] = DemoApp,
) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ready-eval-") as directory:
        path = Path(directory) / "mock.sqlite3"
        app = app_factory(path, agent_config=config)
        session = app.bootstrap(case["user_id"])["session"]
        initial = ledger_snapshot(path)
        for index, turn in enumerate(case["turns"], 1):
            start = time.monotonic()
            try:
                response, _issued = app.chat(session, turn["message"])
                observed = observe(response)
            except (WalletError, AgentError) as error:
                observed = {"outcome": "error", "error_code": error.code}
            except Exception as error:
                # Never serialize arbitrary exception messages: clients may attach
                # provider response bodies or configuration values to exceptions.
                observed = {"outcome": "error", "error_code": "INTERNAL_EXCEPTION",
                            "unexpected_exception": type(error).__name__}
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            changed = ledger_snapshot(path) != initial
            failures = compare(turn["expected"], observed)
            if changed:
                failures.append("Ledger/balance changed during a chat-only evaluation")
            turns.append({
                "turn": index, "message": turn["message"],
                "expected": turn["expected"], "observed": observed,
                "passed": not failures, "failures": failures,
                "duration_ms": duration_ms, "ledger_changed": changed,
            })
    return {"id": case["id"], "category": case["category"],
            "user_id": case["user_id"], "passed": all(t["passed"] for t in turns),
            "turns": turns}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    turns = [turn for result in results for turn in result["turns"]]
    categories: dict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        categories[result["category"]]["total"] += 1
        categories[result["category"]]["passed"] += int(result["passed"])
    passed = sum(bool(result["passed"]) for result in results)
    return {
        "cases": len(results), "passed_cases": passed,
        "case_accuracy_percent": round(100 * passed / len(results), 2) if results else None,
        "turns": len(turns), "passed_turns": sum(bool(t["passed"]) for t in turns),
        "ledger_mutations": sum(bool(t["ledger_changed"]) for t in turns),
        "incorrect_payment_proposals": sum(
            not t["passed"] and t["observed"]["outcome"] in {"draft", "schedule_draft"}
            for t in turns
        ),
        "domain_or_provider_error_responses": sum(
            t["observed"]["outcome"] == "error" for t in turns
        ),
        "expected_domain_rejections": sum(
            t["observed"]["outcome"] == "error" and t["passed"] for t in turns
        ),
        "successful_model_turns": sum(
            t["observed"].get("agent_last_request") == "succeeded" for t in turns
        ),
        "guarded_turns_without_model": sum(
            t["observed"].get("agent_last_request") == "guarded" for t in turns
        ),
        "latency_ms": {
            "p50": percentile([t["duration_ms"] for t in turns], 0.50),
            "p95": percentile([t["duration_ms"] for t in turns], 0.95),
            "method": "nearest rank; complete application chat call; no network in offline mode",
        },
        "categories": {key: dict(value) for key, value in sorted(categories.items())},
    }


def source_metadata() -> dict[str, Any]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    fingerprint = hashlib.sha256()
    source_paths = list(ROOT.glob("*.py")) + list((ROOT / "web").glob("*"))
    source_paths += list((ROOT / "evaluation").glob("*.py"))
    for path in sorted(source_paths):
        if path.is_file():
            fingerprint.update(str(path.relative_to(ROOT)).encode("utf-8") + b"\0")
            fingerprint.update(path.read_bytes())
    return {"git_commit": commit, "working_tree_dirty": dirty,
            "application_source_sha256": fingerprint.hexdigest(),
            "fingerprint_scope": "root Python modules, web assets and evaluation Python modules"}


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# READY development evaluation", "",
        "**Development cases; AI-authored; not human-reviewed; not held out.**", "",
        "This measures structured request-to-review, clarification or safe-response behavior. "
        "It does not press Confirm, grade generated prose, or measure completed payments.", "",
        f"Run: {report['run_at']} · Mode: `{report['mode']}` · Model: `{report['model'] or 'none (offline)'}`",
        f"Source commit: `{report['source']['git_commit']}` · Working tree dirty: `{report['source']['working_tree_dirty']}`",
        f"Application fingerprint: `{report['source']['application_source_sha256']}`",
        f"Dataset SHA-256: `{report['dataset_sha256']}`", "",
        "| Metric | Observed |", "| --- | ---: |",
        f"| Cases passing every turn | {summary['passed_cases']}/{summary['cases']} ({summary['case_accuracy_percent']}%) |",
        f"| Individual turns passing | {summary['passed_turns']}/{summary['turns']} |",
        f"| Turns with a ledger mutation | {summary['ledger_mutations']} |",
        f"| Incorrect payment proposals | {summary['incorrect_payment_proposals']} |",
        f"| Domain/provider error responses (expected domain rejections) | {summary['domain_or_provider_error_responses']} ({summary['expected_domain_rejections']}) |",
        f"| Successful model turns / guarded turns without model | {summary['successful_model_turns']} / {summary['guarded_turns_without_model']} |",
        f"| Chat latency p50 / p95 | {summary['latency_ms']['p50']} / {summary['latency_ms']['p95']} ms |", "",
        "Zero ledger mutations does not establish correct interpretation: wrong prepared "
        "recipients or amounts are counted separately. Safe-reply labels only assert "
        "abstention from proposing a payment; native-speaker review is still required.", "",
        "## Categories", "", "| Category | Passing cases |", "| --- | ---: |",
    ]
    for name, counts in summary["categories"].items():
        lines.append(f"| {name} | {counts.get('passed', 0)}/{counts['total']} |")
    lines += ["", "## Failures", ""]
    failures = [result for result in report["results"] if not result["passed"]]
    if not failures:
        lines.append("No structured failures observed on this development run.")
    for result in failures:
        for turn in result["turns"]:
            if not turn["passed"]:
                message = turn["message"].replace("\n", " ").replace("`", "'")
                lines.append(f"- **{result['id']} / turn {turn['turn']}** — {message}")
                lines.extend(f"  - {failure}" for failure in turn["failures"])
    lines += ["", "Full structured observations and exact expected labels are in the matching JSON report.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "llm"), default="offline")
    parser.add_argument("--allow-network", action="store_true", help="Allow configured provider calls and their token usage")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case", action="append", dest="case_ids", help="Run only a selected case ID; repeatable")
    parser.add_argument("--limit", type=int, help="Run only the first N selected cases, useful for a live smoke run")
    parser.add_argument("--output", type=Path, help="Output filename prefix, without extension")
    args = parser.parse_args(argv)
    if args.mode == "llm" and not args.allow_network:
        parser.error("Live evaluation requires --allow-network; it sends synthetic requests to the configured provider.")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    config = LLMConfig(mode="offline") if args.mode == "offline" else replace(LLMConfig.from_env(), mode="llm")
    if error := config.configuration_error():
        parser.error(error)
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    if args.case_ids:
        known = {case["id"] for case in cases}
        missing = set(args.case_ids) - known
        if missing:
            parser.error("Unknown case IDs: " + ", ".join(sorted(missing)))
        cases = [case for case in cases if case["id"] in args.case_ids]
    if args.limit:
        cases = cases[:args.limit]
    started = datetime.now(timezone.utc)
    results = []
    for index, case in enumerate(cases, 1):
        result = evaluate_case(case, config)
        results.append(result)
        print(f"{index}/{len(cases)} {case['id']}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)
    report = {
        "schema_version": 1, "run_at": started.isoformat(), "mode": args.mode,
        "model": config.model if args.mode == "llm" else None,
        "dataset_status": "development_candidates_not_held_out",
        "human_reviewed": False, "payment_confirmation_exercised": False,
        "dataset_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "source": source_metadata(), "summary": summarize(results), "results": results,
    }
    prefix = args.output or Path(__file__).with_name("results") / f"{started.strftime('%Y%m%dT%H%M%SZ')}_{args.mode}"
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path, md_path = prefix.with_suffix(".json"), prefix.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Reports: {json_path}\n         {md_path}")
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
