# READY development evaluation

**Development cases; AI-authored; not human-reviewed; not held out.**

This measures structured request-to-review, clarification or safe-response behavior. It does not press Confirm, grade generated prose, or measure completed payments.

Run: 2026-10-23T03:11:27.615528+00:00 · Mode: `llm` · Model: `gemini-3.8-flash`
Source commit: `c1de8de9c4bf7e620aafdc5a7c05583d01ec01ca` · Working tree dirty: `False`
Application fingerprint: `901f08eddf99cd7d3f348aa66ae2c0b43f5b510df23caa5a02822de4c16e4209`
Dataset SHA-256: `fd764f656cde695ef53b150e61e69a32ec6131b9e81fcd8e0a28ae6a9e0cd98a`

| Metric | Observed |
| --- | ---: |
| Cases passing every turn | 0/1 (0.0%) |
| Individual turns passing | 0/1 |
| Turns with a ledger mutation | 0 |
| Incorrect payment proposals | 0 |
| Domain/provider error responses (expected domain rejections) | 1 (0) |
| Successful model turns / guarded turns without model | 0 / 0 |
| Chat latency p50 / p95 | 37484.0 / 37484.0 ms |

Zero ledger mutations does not establish correct interpretation: wrong prepared recipients or amounts are counted separately. Safe-reply labels only assert abstention from proposing a payment; native-speaker review is still required.

## Categories

| Category | Passing cases |
| --- | ---: |
| balance | 0/1 |

## Failures

- **R001 / turn 1** — شكد رصيدي هسه؟
  - Expected outcome view; observed error
  - view_kind: expected 'balance'; observed None

Full structured observations and exact expected labels are in the matching JSON report.
