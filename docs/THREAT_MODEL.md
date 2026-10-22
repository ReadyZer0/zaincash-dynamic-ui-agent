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

## Model and mobile increment — 21 October 2026

| Threat | Additional control and practical limit |
| --- | --- |
| Model invents a tool or changes an amount/recipient | Validate the complete tool batch before dispatch; require fresh owner-scoped lookup; ground recipient/bill/amount in user words. Conservative guards may ask extra questions. |
| Provider redirects an Authorization header | Provider client rejects redirects. Remote endpoints require HTTPS; only a literal loopback model endpoint may use HTTP. |
| API key leaks into APK/model context | Key is a backend environment value, excluded from repr/status/tool history. No client key field or bundled key. Raw provider errors are redacted. |
| Saved Gemini key exposed through app settings | Only the foreground backend launcher can read the current Windows user's named Credential Manager entry after explicit live/network opt-in. Browser/APK routes have no key field. Same-user local processes can still read the credential; use a limited free-tier key and rotate if the host is compromised. |
| Infinite agent loop, slow call or concurrent turn | Four model rounds, eight tool calls and bounded timeout; fixed session lock stripes; explicit failure, no automatic retry/fallback. |
| Model says payment succeeded without execution | Server owns reviews/receipts; prepare ends with canonical wording; unsupported obvious success prose is replaced. Generated prose is never a receipt. |
| Risk log fails after a committed debit | Return authoritative receipt and mark advisory recording unavailable. The financial record, not an advisory write, controls retries. |
| Support draft leaks data or sends itself | Owner-scoped original-record lookup; secret-bearing issue text rejected; no network/send or external-ticket tool exists. |
| Android WebView loads attacker-controlled content | Selected-origin URL checks, no native JS bridge, no file/content access, no third-party cookies, TLS errors cancelled. APK is a debug testing client. |

The readable scam rules are demo heuristics, not calibrated fraud detection.
There is no claim that arbitrary prompts, stolen valid sessions, malicious
devices or real-world attackers are perfectly handled. This is a local
demonstrator with synthetic records, not production authentication, payment
settlement, KYC or an official integration.
