# Architecture and trust boundaries

`web/` is a static client only. It sends session-scoped requests to `server.py`; it never receives a database connection, execution secret, or approval authority. `agent.py` is an offline deterministic interpreter that may return text, a clarification, or a registered action ID. It has no payment-commit capability.

`action_registry.py` defines the only visible/actionable controls. `server.py` authenticates the demo session, validates a registry action and its inputs, then delegates to `core.py`. `core.py` owns SQLite records, recipient lookup, draft versions, confirmations, ledger changes, idempotency, receipts, schedule configuration, and read-only status recovery.

The payment transaction path is: chat or menu → registered action → authenticated read/prepare operation → server policy/balance checks → immutable server payment draft → rendered review → final Confirm request → transactional mock debit and receipt. A typed chat message, a model/router response, or client-side state cannot bypass final confirmation.

The M2 schedule path is intentionally separate: registered schedule action → authenticated schedule review → immutable schedule draft → dedicated schedule-config Confirm request → zero-debit `ACTIVE_MOCK_ONLY` plan. It never calls the payment ledger or creates a transaction. The plan stores `REMIND_AND_PREPARE`; a later due occurrence would need a completely fresh ordinary payment draft and final confirmation.

Payment drafts and schedule drafts have separate server-owned active pointers, both bound to the issuing demo session. Preparing a schedule does not supersede a payment review, and each kind validates its own current pointer at confirmation.

`create_server()` resolves only literal loopback bind addresses and the HTTP server refuses non-loopback peers before dispatch. The handler also accepts only local Host headers and same-origin/no-Origin requests. These are local-demo boundary controls, not a substitute for production authentication or transport security.

All timestamps are stored as UTC ISO-8601 values. Money is stored as IQD integer minor units (no binary float). The only mode is visibly labeled `OFFLINE_DEMO`; its data and payment service are synthetic.
