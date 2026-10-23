# READY development evaluation

**Development cases; AI-authored; not human-reviewed; not held out.**

This measures structured request-to-review, clarification or safe-response behavior. It does not press Confirm, grade generated prose, or measure completed payments.

Run: 2026-10-23T03:20:05.940079+00:00 · Mode: `offline` · Model: `none (offline)`
Source commit: `dbabd67aea017832c6f684cd3685abc79029cb8d` · Working tree dirty: `False`
Application fingerprint: `01fddb5b71799144a91aefe8d1ac08ac2f33464d1fd6615454dcebbee8f9e8d4`
Dataset SHA-256: `fd764f656cde695ef53b150e61e69a32ec6131b9e81fcd8e0a28ae6a9e0cd98a`
Provider HTTP attempts reserved in this process: 0 / uncapped (includes failed attempts; not account-wide usage)

| Metric | Observed |
| --- | ---: |
| Cases passing every turn | 74/74 (100.0%) |
| Individual turns passing | 80/80 |
| Turns with a ledger mutation | 0 |
| Incorrect payment proposals | 0 |
| Domain/provider error responses (expected domain rejections) | 1 (1) |
| Successful model turns / guarded turns without model | 0 / 0 |
| Chat latency p50 / p95 | 16.0 / 62.0 ms |

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
