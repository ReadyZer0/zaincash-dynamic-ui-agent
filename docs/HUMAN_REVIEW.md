# Human review and final evaluation preparation

Prepared 22 October 2026. **Protocol only: no participant, dialect-review or
held-out results are recorded here.** ChatGPT/Codex assisted this protocol and
the validation helper. The 74 existing development cases remain visible
regression material. Do not rename them as final or human-reviewed examples.

## Roles and privacy

The dataset custodian manages fresh final examples separately from development.
An Iraqi Arabic speaker edits the request wording; a human reviewer checks every
expected outcome against the fictional wallet. One person may hold both review
roles, but record that honestly. Use reviewer IDs such as `R01`, not names,
phone numbers, emails or private accounts in public evidence. Keep participation
consent separately, locally. Participants may stop or skip a task at any time.
Never ask them for a real PIN, token, identity document or wallet record.

The custodian must keep final labels out of model context and out of tuning.
The validator can check declarations and file hashes, not prove independence or
authenticate a reviewer. Near-duplicate paraphrases need human inspection even
when the exact-text overlap check passes.

## Fifty genuinely edited Iraqi-Arabic requests

1. Draft fresh synthetic requests from the Topic 04 task requirements, not by
   copying the development cases. Record the authoring tools and generation
   method. Retain the original wording of each request that a person edits.
2. Ask Iraqi speakers to rewrite at least 50 **distinct requests** in wording
   they would actually use. Record both versions and a short reason. Clicking
   approve, changing whitespace or replacing an identity with a real one does
   not meet the editing requirement. No AI-generated reviewer IDs or dates.
3. Check each rewritten request and expected action, recipient, amount, fee and
   ledger outcome against the synthetic fixture. If an edit changes intent,
   update the expected label and have a person review it again.
4. Finalize the candidate file before signing its review records. Every one of
   the 200 case labels needs a reviewer ID, real date and exact case hash. All
   human edits must identify the final request text and its zero-based turn.

Review entries have this structure (replace every placeholder only with an
actual observation; this is a schema illustration, not completed evidence):

```json
{
  "reviewers": [
    {"id": "REVIEWER_ID", "role": "RECORDED_ROLE", "human": true, "iraqi_arabic_speaker": true}
  ],
  "human_edits": [
    {
      "case_id": "CASE_ID", "turn_index": 0,
      "reviewer_id": "REVIEWER_ID", "reviewed_on": "YYYY-MM-DD",
      "before": "ORIGINAL_SYNTHETIC_REQUEST", "after": "ACTUAL_HUMAN_EDIT",
      "edit_reason": "ACTUAL_REASON"
    }
  ]
}
```

## Final 200-dialogue workflow

Use the same case structure as `evaluation/cases.jsonl`, plus one
`evaluation_group` per case: `payment` (80), `read_help` (50) or `adversarial`
(70). Keep the more detailed `category` field. All profiles and references must
remain synthetic. The evaluator checks structured outcomes; humans still need
to inspect the wording and usefulness of responses.

Keep the candidate set outside the app's runtime directories and public branch
until the custodian decides to publish evidence. The commands below use a local
folder named `final-review`; its files do not exist in this delivery.

```powershell
python -m evaluation.freeze prepare --cases final-review/cases.jsonl --reviews final-review/reviews.json
```

This writes **blank** reviewer/date fields and hashes for the exact draft. It
does not declare human review complete. After real reviews, enter the generation
method, tools, reviewer records, at least 50 before/after edits and all label
reviews. The custodian records `used_for_tuning: false` and
`labels_hidden_from_model: true`, then changes `status` to
`human_review_complete` only when true.

If cases change during review, prepare a new scaffold at a new reviews filename
and re-review changed labels. Carry forward only genuinely valid review records
with the same case hash. Preserve earlier files rather than silently replacing
their history.

```powershell
python -m evaluation.freeze validate --cases final-review/cases.jsonl --reviews final-review/reviews.json
python -m evaluation.freeze freeze --cases final-review/cases.jsonl --reviews final-review/reviews.json --manifest final-review/frozen.json --acknowledge-human-review
python -m evaluation.freeze verify --cases final-review/cases.jsonl --reviews final-review/reviews.json --manifest final-review/frozen.json
```

Do not provide the acknowledgement flag on behalf of nonexistent participants.
`freeze` never overwrites an existing manifest. `verify` checks current files
against that manifest; even byte-only changes invalidate its dataset hash.
After verifying, use the evaluator's `--cases` option for the intended set. A
live run additionally requires approved provider configuration and
`--allow-network`; freeze itself never calls a model. Preserve dated outputs,
revision, application fingerprint, provider config and exact denominators.

The current evaluator labels its reports as development evidence even with a
custom `--cases` file. It does not read the freeze manifest or certify a held-out
run. Keep the manifest alongside the report and have the custodian verify their
matching dataset hash and independence before preparing any final evidence
claim. Do not rewrite a machine report's provenance to imply verification it
did not perform.

If final-set failures guide a fix, mark that evaluation as development evidence
and create a fresh independent final set. The freeze helper cannot enforce this
human process. Keep confirmation/execution checks separate: the language
evaluator never presses Confirm. Targets remain 117/130 functional cases and
zero unauthorized, incorrect or duplicate mock debits, not reported achievements.

## Five to eight observed task-based sessions

Use a physical APK when available; label browser or emulator sessions accurately.
A smaller pilot tests the script only. Include people with lower smartphone
confidence when possible, without claiming a statistically representative study.
Explain that all records/payments are fictional and the person is testing the
app, not being graded. Use a fresh synthetic database for each session, observe
without coaching first, and record every intervention.

| Task | User goal | What the observer checks |
| --- | --- | --- |
| Duplicate Ali | Prepare a transfer to the intended saved Ali | Clarification; intended recipient/amount; ability to read fee and remaining balance before Confirm |
| Saved bill | Pay the fixture's electricity/mobile bill | Correct saved bill and amount; read review; one deliberate mock Confirm |
| Insufficient funds | Attempt an amount above available funds but within the mock cap | Honest rejection; no debit; no invented loan offer; useful next step |
| Suspicious request | Inspect a synthetic urgent/new-recipient request | User understands the specific advisory reason and can cancel; warning is not mistaken for a verified fraud verdict |
| Uncertain result | Recover the original mock transaction after an interrupted response | Original status/reference, no replacement payment, optional support draft understood as unsent |

The facilitator must rehearse the uncertain-result fixture safely on a separate
database before involving participants. Do not disconnect during a real payment,
change a real account, or improvise a production failure. Record the exact test
setup and whether the interruption is simulated or actually induced locally.

Copy one blank record per observed task; do not fill examples with invented data:

| Field | Observation |
| --- | --- |
| Session ID / participant pseudonym / consent recorded separately | |
| Date (Asia/Baghdad) / source commit / APK hash / device or browser | |
| Offline or exact provider/model / fixture / task ID | |
| Completed unaided: yes, no or skipped | |
| Start / correct-review time / end (seconds) | |
| Recipient / amount / fee / remaining-balance understanding | |
| Incorrect taps or attempted payments / corrections / help given | |
| Observed authoritative receipt/status and ledger delta | |
| Participant interpretation after failure / confusing wording | |
| Optional quote recorded with consent; otherwise observer paraphrase | |

Report observed counts with denominators, missing/skipped tasks, median/range
of task times and mistakes. Keep actual observations separate from suggestions.
Do not turn 5–8 sessions into a production-safety or population-accuracy claim.
