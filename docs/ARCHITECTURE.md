# Architecture and trust boundaries

`web/` is a static client only. It sends session-scoped requests to `server.py`; it never receives a database connection, execution secret, or approval authority. `agent.py` is an offline deterministic interpreter that may return text, a clarification, or a registered action ID. It has no payment-commit capability.

`action_registry.py` defines the only visible/actionable controls. `server.py` authenticates the demo session, validates a registry action and its inputs, then delegates to `core.py`. `core.py` owns SQLite records, recipient lookup, draft versions, confirmations, ledger changes, idempotency, receipts, schedule configuration, and read-only status recovery.

The payment transaction path is: chat or menu → registered action → authenticated read/prepare operation → server policy/balance checks → immutable server payment draft → rendered review → final Confirm request → transactional mock debit and receipt. A typed chat message, a model/router response, or client-side state cannot bypass final confirmation.

The M2 schedule path is intentionally separate: registered schedule action → authenticated schedule review → immutable schedule draft → dedicated schedule-config Confirm request → zero-debit `ACTIVE_MOCK_ONLY` plan. It never calls the payment ledger or creates a transaction. The plan stores `REMIND_AND_PREPARE`; a later due occurrence would need a completely fresh ordinary payment draft and final confirmation.

Payment drafts and schedule drafts have separate server-owned active pointers, both bound to the issuing demo session. Preparing a schedule does not supersede a payment review, and each kind validates its own current pointer at confirmation.

`create_server()` resolves only literal loopback bind addresses and the HTTP server refuses non-loopback peers before dispatch. The handler also accepts only local Host headers and same-origin/no-Origin requests. These are local-demo boundary controls, not a substitute for production authentication or transport security.

All timestamps are stored as UTC ISO-8601 values. Money is stored as IQD integer minor units (no binary float). Payment data and execution are synthetic in both agent modes.

## Model mode and Android increment — 21 October 2026

`OFFLINE_DEMO` remains the default. With explicit backend configuration,
`llm_agent.py` calls an OpenAI-compatible provider in `LIVE_MODEL` mode. Its
closed tool loop permits reads, clarification, and preparation only. It has no
confirmation, session-selection, arbitrary-network or code-execution tool.
Provider key, CSRF value and approval credential never enter tool results or
model history. A failed provider call produces an explicit error; no silent
offline fallback is performed.

The model must look up current owner-scoped contacts/bills. The requested
recipient and amount are checked against user-only request evidence before a
transfer is prepared. Unsupported language can cause an extra clarification;
these conservative guards do not establish perfect language understanding.
Calls are bounded to 4 provider rounds, 8 tool calls and a 45-second turn budget.
Session history keeps at most six short user/assistant messages, approximately
2,700 JSON characters, separately from the core's active review pointers.
Fixed lock stripes reject concurrent chat turns for the same session.

`payment_assist.py` computes advisory risk reasons, remaining-balance context
and source-linked summary figures in Python. It stores only rule codes/context
and review decisions, not raw chat text, in separate local tables. Its audit is
best-effort: an unavailable advisory log cannot hide a committed receipt or
prevent original-record status recovery. Cancellation logs the version the user
actually reviewed, before the core increments its version to revoke approval.
This advisory table is not a production compliance audit trail.

Support drafts use a transaction lookup scoped to the current owner. User issue
text is labeled unverified. Drafting does not send a message, create an external
ticket, change a balance or retry a transaction.

The Android native Java shell loads the existing `web/` interface from one
selected origin. Initial testing uses USB `adb reverse` to reach the computer's
loopback backend. No Python runtime or model key is packaged in the APK. Remote
HTTPS selection is only a client setting for a future independently secured
deployment; the current server retains its loopback/Host/Origin restrictions.
