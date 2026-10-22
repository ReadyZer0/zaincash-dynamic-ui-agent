"""Prepare and verify a final-set manifest, never manufacture human evidence.

This local tool makes no provider calls. It verifies recorded review fields and
hashes, not the truth of a human review or an independence declaration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from evaluation.run import DEFAULT_CASES, load_cases

GROUPS = {"payment": 80, "read_help": 50, "adversarial": 70}
BAGHDAD = timezone(timedelta(hours=3), "Asia/Baghdad")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def case_digest(case: dict) -> str:
    raw = json.dumps(case, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def dialogue_key(case: dict) -> tuple[str, ...]:
    return tuple(normalized(turn["message"]) for turn in case["turns"])


def final_cases(path: Path, development: Path = DEFAULT_CASES) -> list[dict]:
    cases = load_cases(path)
    counts = Counter(case.get("evaluation_group") for case in cases)
    if dict(counts) != GROUPS:
        raise ValueError(
            "Final set must contain 80 payment, 50 read_help and 70 adversarial cases"
        )
    keys = [dialogue_key(case) for case in cases]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate dialogue text is not an independent case")
    development_keys = {dialogue_key(case) for case in load_cases(development)}
    if set(keys) & development_keys:
        raise ValueError("Final set overlaps development dialogues; use fresh examples")
    return cases


def review_template(cases_path: Path, development: Path = DEFAULT_CASES) -> dict:
    cases = final_cases(cases_path, development)
    return {
        "schema_version": 1,
        "status": "awaiting_human_review",
        "dataset_sha256": digest(cases_path),
        "generation_method": "",
        "authoring_tools": [],
        "reviewers": [],
        "independence": {
            "custodian_id": "",
            "used_for_tuning": None,
            "labels_hidden_from_model": None,
        },
        "human_edits": [],
        "label_reviews": [
            {
                "case_id": case["id"],
                "case_sha256": case_digest(case),
                "reviewer_id": None,
                "reviewed_on": None,
            }
            for case in cases
        ],
    }


def validate(
    cases_path: Path, reviews_path: Path, development: Path = DEFAULT_CASES
) -> dict:
    cases = final_cases(cases_path, development)
    by_id = {case["id"]: case for case in cases}
    review = json.loads(reviews_path.read_text(encoding="utf-8"))
    if (
        review.get("schema_version") != 1
        or review.get("status") != "human_review_complete"
    ):
        raise ValueError("Human review is not recorded as complete")
    if review.get("dataset_sha256") != digest(cases_path):
        raise ValueError(
            "Review refers to different dataset bytes; review the changed version"
        )
    if not review.get("generation_method") or not isinstance(
        review.get("authoring_tools"), list
    ):
        raise ValueError("Record the generation method and authoring tools")
    independence = review.get("independence", {})
    if (
        not independence.get("custodian_id")
        or independence.get("used_for_tuning") is not False
        or independence.get("labels_hidden_from_model") is not True
    ):
        raise ValueError(
            "A custodian must record fresh, untuned cases and hidden labels"
        )
    people = review.get("reviewers", [])
    reviewers = {person.get("id"): person for person in people}
    if (
        not people
        or len(reviewers) != len(people)
        or not all(isinstance(key, str) and key.strip() for key in reviewers)
    ):
        raise ValueError("Use unique nonempty pseudonymous human reviewer IDs")

    def checked_reviewer(row: dict) -> dict:
        person = reviewers.get(row.get("reviewer_id"))
        if not person or person.get("human") is not True or not person.get("role"):
            raise ValueError("Every review needs a recorded human reviewer and role")
        try:
            reviewed = date.fromisoformat(row["reviewed_on"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Every review needs an actual ISO review date") from error
        if reviewed > datetime.now(BAGHDAD).date():
            raise ValueError("A review date cannot be in the future")
        return person

    labels = review.get("label_reviews", [])
    if len(labels) != len(cases) or {row.get("case_id") for row in labels} != set(
        by_id
    ):
        raise ValueError("All 200 case labels need one human review record each")
    for row in labels:
        checked_reviewer(row)
        if row.get("case_sha256") != case_digest(by_id[row["case_id"]]):
            raise ValueError("A label review is stale; recheck the changed case")
    edited_requests: set[str] = set()
    edited_turns: set[tuple[str, int]] = set()
    for row in review.get("human_edits", []):
        person = checked_reviewer(row)
        if person.get("iraqi_arabic_speaker") is not True:
            raise ValueError("Dialect edits need a recorded Iraqi Arabic speaker")
        case = by_id.get(row.get("case_id"))
        index = row.get("turn_index")
        if not case or type(index) is not int or not 0 <= index < len(case["turns"]):
            raise ValueError("An edit must identify a valid case and zero-based turn")
        key = (case["id"], index)
        if key in edited_turns:
            raise ValueError("Do not count the same edited turn twice")
        before, after = row.get("before"), row.get("after")
        if (
            not isinstance(before, str)
            or not before.strip()
            or after != case["turns"][index]["message"]
        ):
            raise ValueError(
                "Edit evidence must retain before text and exact final after text"
            )
        if normalized(before) == normalized(after) or not row.get("edit_reason"):
            raise ValueError(
                "Record a substantive edit and reason, not approval or whitespace only"
            )
        edited_turns.add(key)
        edited_requests.add(normalized(after))
    if len(edited_requests) < 50:
        raise ValueError(
            "At least 50 distinct requests need recorded Iraqi-human edits"
        )
    return {
        "schema_version": 1,
        "status": "review_record_valid_not_evaluated",
        "dataset_sha256": digest(cases_path),
        "reviews_sha256": digest(reviews_path),
        "development_sha256": digest(development),
        "cases": len(cases),
        "groups": GROUPS,
        "recorded_human_edited_requests": len(edited_requests),
        "reviewer_count": len(reviewers),
        "limitations": "Validates records, not reviewer identity, linguistic quality or actual independence; no evaluation or confirmation test performed.",
    }


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "validate", "freeze", "verify"))
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--acknowledge-human-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            write_new(args.reviews, review_template(args.cases))
            print("Blank review scaffold created; no human review is claimed.")
            return 0
        result = validate(args.cases, args.reviews)
        if args.command in {"freeze", "verify"}:
            if args.manifest is None:
                parser.error("--manifest is required for freeze/verify")
            if args.command == "freeze":
                if not args.acknowledge_human_review:
                    parser.error(
                        "freeze requires --acknowledge-human-review after actual human review"
                    )
                result["status"] = "frozen_candidate_not_evaluated"
                result["frozen_at"] = datetime.now(timezone.utc).isoformat()
                write_new(args.manifest, result)
            else:
                result["status"] = "frozen_candidate_not_evaluated"
                stored = json.loads(args.manifest.read_text(encoding="utf-8"))
                if not stored.get("frozen_at") or any(
                    stored.get(key) != value for key, value in result.items()
                ):
                    raise ValueError(
                        "Frozen manifest no longer matches; preserve it and create a new version"
                    )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Final-set gate failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
