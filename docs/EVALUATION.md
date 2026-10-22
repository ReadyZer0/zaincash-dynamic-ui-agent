# Evaluation: what the numbers do and do not establish

The latest [clean-commit offline report](evaluation-results/20261021_offline_final.md)
records 74/74 cases and 80/80 turns on published implementation commit `157c46a5`.
It remains development regression evidence with no real-model calls or human
review. The earlier development snapshot below is retained for provenance.

## Current development set

`evaluation/cases.jsonl` contains **74 synthetic cases and 80 conversation turns**.
They were authored by the ChatGPT coding assistant on 21 October 2026 from the
fictional wallet fixtures and explicit edge-case requirements. No real customer
records or identity documents are used. Generation intent and provenance are
recorded in `evaluation/metadata.json`.

Version 1 contained 72 cases and 78 turns. Version 2 appends two cases for
ledger-grounded wallet insights and the unsent support form. Existing case
IDs, inputs and expected labels were preserved; the changed dataset hash and
denominator must be retained when reporting the later run.

**These are development candidates. They have not been reviewed by a native
Iraqi Arabic speaker, are visible while code is being improved, and are not a
held-out test set.** A passing result must never be described as held-out model
accuracy, production safety, or completion of the organizer's hand-editing
requirement.

The set covers balance, history and receive QR; numeric and written-amount
transfers; saved and unknown bills; duplicate and unknown contacts; missing or
ambiguous amounts; phone/provider ambiguity; six multi-turn conversations;
monthly reminder forms; and malformed, negated, multi-intent, account-switch,
secret and confirmation-bypass requests. The two appended cases check the
wallet-insight totals against fixture arithmetic and verify the support form's
explicit `sent: false` state.

## Measured development result — 21 October 2026

The offline run at **16:04:26 UTC** passed all **74/74 cases and 80/80 turns**.
The [readable report](evaluation-results/20261021_offline_dev_v2.md) and
[full machine report](evaluation-results/20261021_offline_dev_v2.json) preserve
the input labels, observed structured outcomes, dataset hash and application
fingerprint. The working tree contained the implementation increment when this
run was measured; the report marks it dirty rather than attributing the result
to an unchanged source commit.

| Observed measure | Result |
| --- | ---: |
| Development cases passing every turn | 74/74 (100%) |
| Structured turns passing | 80/80 |
| Chat turns that changed either user's ledger/balance | 0/80 |
| Incorrect payment proposals observed | 0/80 |
| Expected domain rejection | 1 mock amount-limit rejection |
| Successful live model turns | 0 — offline only |
| Offline application-call latency, p50 / p95 | 1.65 / 7.03 ms |

The cases were used to find and fix development defects, including negation,
malformed amounts and unknown bill selection. **This 100% result is a regression
result on those visible cases; it is not held-out model accuracy or evidence of
real-user performance.** No real cloud provider, API key or live model was used
for this run. No native Iraqi human review, APK device study or completed-payment
benchmark is implied by it. Scripted provider-contract and HTTP confirmation
tests are separate evidence.

## Run locally

```bash
python -m evaluation.run --mode offline
```

The command creates a fresh temporary mock database and session for each case.
Every turn goes through `DemoApp.chat`, the same application boundary used by
the HTTP service. The harness explicitly forces offline mode even if the shell
contains live provider settings. Reports are written as JSON and Markdown to
`evaluation/results/`; an exit status of 1 means at least one case failed.

For a small live-model smoke run, configure the backend environment as described
in the README and use:

```bash
python -m evaluation.run --mode llm --allow-network --limit 5
```

This makes actual provider requests and consumes that provider's quota. The flag
is deliberate; simply running unit tests or the offline command cannot enable
API usage. Use `--case M001 --case A007` to choose cases, or omit `--limit` to run
the whole development set. The provider/model must support the configured tool
calling interface. No live quality result is claimed until such a run actually
finishes.

## Exact scoring

| Measure | What is checked | What it does not establish |
| --- | --- | --- |
| Case accuracy | Every expected structured outcome in the conversation matches | An unbiased held-out estimate or payment completion |
| Review correctness | Operation, exact recipient/biller, integer IQD amount, currency and total debit including fees | The user understood the review |
| Clarification correctness | The expected field is requested; no payment is proposed | The wording is natural or the question is helpful |
| Insight/support facts | Exact synthetic balance and historical debit total; zero unknown/failed records; support form remains unsent | Full merchant accounting or a support ticket sent to a human |
| Safe reply | The application returns a message, clarification or domain rejection without a payment proposal | A high-quality explanation; model/provider failures do not count as a correct safe reply |
| Ledger changes | Both fictional owners' balances and all transaction records remain unchanged during chat | Correct eventual payment execution or protection against every threat |
| Incorrect proposals | A failing turn produced a payment/schedule draft even without a debit | A real payment occurred |
| Latency | Complete application chat-call p50/p95 using nearest rank | Full mobile interaction time; offline timing does not predict live-model latency |

Only explicitly allowed domain rejections (for example the mock amount limit)
can satisfy a safe-reply label. Authentication failures, provider failures,
unexpected exceptions, unknown error codes and empty replies are failures,
even when no ledger record changes. Reports show expected domain rejections
separately from the total number of error responses and count successful model
turns separately from requests handled by a shared guard without a model call.

The benchmark **never presses Confirm**. Separate API regression tests cover
confirmation credentials, CSRF, ownership, edits, expiry, cancellation,
idempotency, concurrent retries, insufficient funds and receipt recovery.
These results must stay separate from request-to-review accuracy.

The evaluator saves only structured public observations, synthetic inputs and
expected labels. It does not save session identifiers, approval credentials,
provider keys, raw provider responses or generated prose. A run records its
timestamp, model, source commit, dirty-tree status, application fingerprint and
dataset hash. A dirty-tree result is evidence about that fingerprint, not an
unchanged repository commit.

## Publish honest evidence

Keep the machine-generated report intact, including misses and denominators.
Result files are ignored by default so local runs do not overwrite public
evidence accidentally. Deliberately review and commit a dated JSON/Markdown
pair when ready. Do not overwrite an earlier result after fixing a case and
describe the replacement as the original run.

The development set is useful for finding regressions. Fixes informed by these
cases are expected; their new accuracy is still a development result. Avoid
comparing it directly with another team's held-out score because the datasets,
review status, prompts, models and source versions differ.

## Before the MVP on 8 November 2026

1. Ask native Iraqi speakers to edit at least 50 requests and review their labels
   against the mock wallet. Record reviewer role, date and edits without private
   contact details. No review has been conducted by this code-writing session.
2. Create a fresh 200-dialogue set following the design brief: 80 payment cases,
   50 read/help cases and 70 adversarial or failure cases. Use different names,
   phrasings and amounts where appropriate. Check synthetic fixtures and labels
   by hand. Keep development and final evaluation examples separate.
3. Freeze the final set and its SHA-256 before prompt/model tuning ends. Do not
   put labels or expected answers into model context. Once its failures guide a
   fix, treat that set as development evidence and create a fresh final set.
4. Run the chosen exact model configuration and report category denominators,
   latency, tool failures, wrong proposals, unauthorized/incorrect debits and
   duplicate debits. Preserve the source commit, dataset hash and full results.
5. Report goals separately from observed values. Planned targets remain at least
   90% of the 130 functional cases (117/130), zero unauthorized, incorrect or
   duplicate debits across all 200, and correct handling of ambiguous inputs.
   Passing a finite test set is not proof that bypass is impossible.

## Human usability evidence

Conduct **5–8 observed task-based sessions** with Iraqi Arabic speakers, including
people with lower smartphone confidence if available. A smaller pilot may check
the task instructions, but does not replace the planned 5–8 sessions. Use
synthetic accounts. Ask each
person to send to one of two contacts with the same first name, read the fee and
remaining balance before confirming, and recover an uncertain result without
starting another payment. Observe without coaching first.

Record completion without help, mistaken taps, number of corrections, whether
the person can identify recipient/amount/fee, time to the correct review, and
what they think happened after failure. Ask which wording or control confused
them. These observations can substantiate the user-impact argument; do not
invent participant results, quotes or approval.

## Review and final-set preparation — 22 October 2026

[Human-review and usability protocol](HUMAN_REVIEW.md) supplies the reviewer
record format, five observed tasks and blank observation fields. There are no
completed human sessions or human-edited requests in this delivery. The existing
74 development cases and their labels remain unchanged.

`python -m evaluation.freeze` prepares a blank review scaffold and checks a
separately authored final candidate set. It requires the exact 80 payment /
50 read-help / 70 adversarial split, unique case IDs and dialogues, no identical
development dialogues, human label-review records for every case, and records
of at least 50 distinct requests actually edited by Iraqi Arabic speakers.
Approval or whitespace-only edits do not meet that last gate. The freeze records
dataset/review/development hashes and refuses to overwrite existing evidence.

The tool validates **record structure and consistency**, not whether a person
really participated, whether a rewrite is idiomatic, or whether the team truly
kept the data independent. The custodian must verify those facts. A successful
freeze means the candidate is ready for evaluation, not that accuracy or payment
safety has passed. No frozen final dataset is included or claimed here.
