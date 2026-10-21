# Safe-core threat model

| Threat | Control in this increment |
| --- | --- |
| Prompt/model or chat injection asks to pay | The offline router can only select registered read/prepare actions. There is no model commit tool. |
| Typed “yes” or forged client confirmation | Only the authenticated confirmation endpoint accepts the current server-generated owner/version-bound HttpOnly approval credential plus CSRF protection. |
| Stale tab, newer draft, or new session | Payment and schedule drafts have separate session-bound current pointers; a superseded review fails safely without invalidating the other kind. |
| Edited, cancelled, expired, or stale-policy draft | Draft version/state/expiry/policy are rechecked by the server; edits and cancellation invalidate old approval. |
| Schedule accidentally becomes a payment | Schedule drafts, confirmation cookie/routes, and persisted plans are separate from the ledger. A confirmed plan has zero debit and no timer, notification, provider call, or auto-debit. |
| Double tap, retry, or race | SQLite transaction + unique idempotency key return the stored payment receipt or the one stored schedule plan without a second effect. |
| Overdraw through parallel payment drafts | Current balance and policy are checked inside the payment confirm transaction. |
| Cross-user access or receipt/schedule lookup | Session identity determines ownership; request payload user IDs are ignored/rejected and record lookups are owner-scoped. |
| Local-network or DNS-rebinding exposure | Server construction permits literal loopback binds only; non-loopback peers and unsafe Host/Origin values are rejected. |
| Unknown result retried as a new payment | The client queries the original mock transaction or schedule-draft status; it does not make a new draft automatically. |
| Sensitive data exposure | Fixtures are fictional, no PIN/OTP is collected, approval tokens are not included in chat responses, and APIs return only necessary review/status data. |

This is a local demonstrator, not a production security claim. Real authentication, HTTPS deployment protections, encrypted storage, provider settlement, KYC, and official integration are outside the approved scope.
