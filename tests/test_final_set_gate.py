"""Synthetic test doubles for the final-set gate; not human-review evidence."""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from evaluation.freeze import (
    GROUPS,
    case_digest,
    digest,
    final_cases,
    main,
    review_template,
    validate,
    write_new,
)


class FinalSetGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cases_path = self.root / "test-only-cases.jsonl"
        self.review_path = self.root / "test-only-review.json"
        self.cases = []
        for group, count in GROUPS.items():
            for index in range(count):
                self.cases.append(
                    {
                        "id": f"TEST-{group}-{index}",
                        "category": "test_fixture",
                        "evaluation_group": group,
                        "user_id": "demo_amina",
                        "turns": [
                            {
                                "message": f"TEST ONLY synthetic text {group} {index}",
                                "expected": {"outcome": "message"},
                            }
                        ],
                    }
                )
        self.save_cases()
        self.review = review_template(self.cases_path)
        self.review.update(
            {
                "status": "human_review_complete",
                "generation_method": "UNIT TEST DOUBLE ONLY; no human participated",
                "authoring_tools": ["unittest synthetic fixture"],
                "reviewers": [
                    {
                        "id": "TEST_REVIEWER",
                        "role": "test double",
                        "human": True,
                        "iraqi_arabic_speaker": True,
                    }
                ],
                "independence": {
                    "custodian_id": "TEST_CUSTODIAN",
                    "used_for_tuning": False,
                    "labels_hidden_from_model": True,
                },
                "human_edits": [
                    {
                        "case_id": case["id"],
                        "turn_index": 0,
                        "reviewer_id": "TEST_REVIEWER",
                        "reviewed_on": "2026-01-01",
                        "before": f"BEFORE TEST ONLY {index}",
                        "after": case["turns"][0]["message"],
                        "edit_reason": "unit-test fixture only",
                    }
                    for index, case in enumerate(self.cases[:50])
                ],
            }
        )
        for row in self.review["label_reviews"]:
            row.update(reviewer_id="TEST_REVIEWER", reviewed_on="2026-01-01")
        self.save_review()

    def save_cases(self) -> None:
        self.cases_path.write_text(
            "".join(json.dumps(case) + "\n" for case in self.cases), encoding="utf-8"
        )

    def save_review(self) -> None:
        self.review_path.write_text(json.dumps(self.review), encoding="utf-8")

    def test_complete_record_structure_has_exact_hashes_and_honest_limit(self) -> None:
        result = validate(self.cases_path, self.review_path)
        self.assertEqual(result["groups"], GROUPS)
        self.assertEqual(result["recorded_human_edited_requests"], 50)
        self.assertEqual(result["dataset_sha256"], digest(self.cases_path))
        self.assertEqual(result["status"], "review_record_valid_not_evaluated")
        self.assertIn("not reviewer identity", result["limitations"])

    def test_blank_scaffold_does_not_pass_as_reviewed(self) -> None:
        self.review = review_template(self.cases_path)
        self.save_review()
        self.assertEqual(self.review["human_edits"], [])
        with self.assertRaisesRegex(ValueError, "not recorded as complete"):
            validate(self.cases_path, self.review_path)

    def test_wrong_counts_duplicate_ids_and_duplicate_text_are_rejected(self) -> None:
        original = copy.deepcopy(self.cases)
        mutations = (
            lambda: self.cases.pop(),
            lambda: self.cases[1].update(id=self.cases[0]["id"]),
            lambda: self.cases[1].update(turns=self.cases[0]["turns"]),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.cases = copy.deepcopy(original)
                mutate()
                self.save_cases()
                with self.assertRaises(ValueError):
                    final_cases(self.cases_path)

    def test_development_dialogue_copy_is_rejected_even_with_new_id(self) -> None:
        self.cases[0]["turns"][0]["message"] = " شكد   رصيدي هسه؟ "
        self.save_cases()
        with self.assertRaisesRegex(ValueError, "overlaps development"):
            final_cases(self.cases_path)

    def test_changed_dataset_or_label_review_cannot_reuse_old_approval(self) -> None:
        self.cases[0]["turns"][0]["expected"] = {"outcome": "safe_reply"}
        self.save_cases()
        with self.assertRaisesRegex(ValueError, "different dataset bytes"):
            validate(self.cases_path, self.review_path)
        self.review["dataset_sha256"] = digest(self.cases_path)
        self.save_review()
        with self.assertRaisesRegex(ValueError, "label review is stale"):
            validate(self.cases_path, self.review_path)

    def test_fake_edit_counts_and_machine_review_are_rejected(self) -> None:
        original = copy.deepcopy(self.review)
        changes = (
            lambda: self.review["human_edits"].pop(),
            lambda: self.review["human_edits"].append(self.review["human_edits"][0]),
            lambda: self.review["human_edits"][0].update(
                before=self.review["human_edits"][0]["after"]
            ),
            lambda: self.review["human_edits"][0].update(after="not the dataset text"),
            lambda: self.review["reviewers"][0].update(human=False),
            lambda: self.review["reviewers"][0].update(iraqi_arabic_speaker=False),
            lambda: self.review["label_reviews"][0].update(reviewed_on="2099-01-01"),
            lambda: self.review["independence"].update(used_for_tuning=True),
        )
        for change in changes:
            with self.subTest(change=change):
                self.review = copy.deepcopy(original)
                change()
                self.save_review()
                with self.assertRaises(ValueError):
                    validate(self.cases_path, self.review_path)

    def test_manifest_creation_never_overwrites_existing_evidence(self) -> None:
        manifest = self.root / "frozen.json"
        write_new(manifest, {"original": True})
        original = manifest.read_bytes()
        with self.assertRaises(FileExistsError):
            write_new(manifest, {"original": False})
        self.assertEqual(manifest.read_bytes(), original)

    def test_case_hash_covers_expected_amount_and_message(self) -> None:
        case = copy.deepcopy(self.cases[0])
        before = case_digest(case)
        case["turns"][0]["expected"]["amount_minor"] = 5000
        self.assertNotEqual(before, case_digest(case))
        before = case_digest(case)
        case["turns"][0]["message"] += " altered"
        self.assertNotEqual(before, case_digest(case))

    def test_cli_freeze_verify_and_stale_review_detection(self) -> None:
        manifest = self.root / "test-only-frozen.json"
        common = [
            "--cases",
            str(self.cases_path),
            "--reviews",
            str(self.review_path),
            "--manifest",
            str(manifest),
        ]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["freeze", *common, "--acknowledge-human-review"]), 0)
            self.assertEqual(main(["verify", *common]), 0)
            frozen = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(frozen["status"], "frozen_candidate_not_evaluated")
            self.review["generation_method"] += " changed"
            self.save_review()
            self.assertEqual(main(["verify", *common]), 1)
            self.assertEqual(main(["freeze", *common, "--acknowledge-human-review"]), 1)


if __name__ == "__main__":
    unittest.main()
