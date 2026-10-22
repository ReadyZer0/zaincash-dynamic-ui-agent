# READY development evaluation

**Development cases; AI-authored; not human-reviewed; not held out.**

This measures structured request-to-review, clarification or safe-response behavior. It does not press Confirm, grade generated prose, or measure completed payments.

Run: 2026-10-22T12:15:43.817541+00:00 · Mode: `offline` · Model: `none (offline)`
Source commit: `324a7118a1b5f1e01170db4a2521d933420fccc1` · Working tree dirty: `False`
Application fingerprint: `87a334429dc64e0beaa6f79f13e498cd657620d811344f1972d8cda17249f361`
Dataset SHA-256: `fd764f656cde695ef53b150e61e69a32ec6131b9e81fcd8e0a28ae6a9e0cd98a`

| Metric | Observed |
| --- | ---: |
| Cases passing every turn | 74/74 (100.0%) |
| Individual turns passing | 80/80 |
| Turns with a ledger mutation | 0 |
| Incorrect payment proposals | 0 |
| Domain/provider error responses (expected domain rejections) | 1 (1) |
| Successful model turns / guarded turns without model | 0 / 0 |
| Chat latency p50 / p95 | 16.0 / 46.0 ms |

Zero ledger mutations does not establish correct interpretation: wrong prepared recipients or amounts are counted separately. Safe-reply labels only assert abstention from proposing a payment; native-speaker review is still required.

## Categories

| Category | Passing cases |
| --- | ---: |
| account_switch | 1/1 |
| ambiguous_recipient | 4/4 |
| amount_limit | 1/1 |
| balance | 4/4 |
| bill | 4/4 |
| fractional_amount | 2/2 |
| history | 4/4 |
| injected_confirmation | 1/1 |
| malformed_amount | 1/1 |
| missing_or_ambiguous_amount | 4/4 |
| missing_recipient | 1/1 |
| multiple_payments | 2/2 |
| multiturn | 6/6 |
| negation | 2/2 |
| negative_amount | 2/2 |
| phone_provider | 2/2 |
| receive_qr | 4/4 |
| schedule_form | 4/4 |
| secret | 2/2 |
| support_form | 1/1 |
| transfer | 14/14 |
| typed_confirmation | 2/2 |
| unknown_bill | 2/2 |
| unknown_recipient | 1/1 |
| unsupported_currency | 2/2 |
| wallet_insights | 1/1 |

## Failures

No structured failures observed on this development run.

Full structured observations and exact expected labels are in the matching JSON report.
