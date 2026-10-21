# Iraqi-Arabic Dynamic UI agent — Topic 04

An independent, local-only prototype for the Agentic AI Challenge Iraq's Bill Pay & Transfer Agent topic. Iraqi-Arabic chat and menus use the same server-owned action registry, so a request can bring a real app control into the conversation. Balance and history are read-only. Mock transfers and bills show a complete review and require a separate final **Confirm** button.

This is **not** an official ZainCash app or integration. All profiles, balances, bills, QR payloads, and transactions are fictional. No real money moves. The current router is deterministic and offline; it does not call an external model.

## Run

Python 3.12+ is recommended. No third-party runtime packages are required.

```bash
python server.py
```

Open `http://127.0.0.1:8765` on the same computer. On Windows, `py -3 server.py` also works. The server binds to loopback and creates a local SQLite demo database. Set `READY_DB_PATH` to a different local file for a clean run.

## Test

```bash
python -m unittest discover -s tests -v
```

The 24-test suite passed locally on 21 October 2026. This is a dated result, not a claim about a later commit or deployment.

## Safety boundary

- The offline interpreter can select registered read/prepare actions only. It cannot confirm, commit, or receive approval secrets.
- The backend derives account ownership from the current demo session, not a user ID in the chat message. It validates policy, balance, draft version and expiry at confirmation.
- Payment review and final confirmation are distinct server operations. Retries use an idempotency key, and the mock ledger records at most one debit.
- Monthly scheduling configures a reminder/preparation plan only. It creates no timer, notification, or debit.
- Demo session checks do **not** equal production authentication. A stolen authenticated session would be a serious production threat; this prototype makes no claim of preventing that scenario.

See [architecture](docs/ARCHITECTURE.md), [threat model](docs/THREAT_MODEL.md), and [synthetic data](docs/DEMO_DATA.md).

## Scope

Current: typed Iraqi-Arabic chat, registered Dynamic UI controls, synthetic balance/history, mock transfer/bill review and confirmation, receipt/status recovery, mock receive QR, and zero-debit monthly-plan configuration.

Not enabled: external LLM calls, real payments, production KYC, stock orders, external notifications, and original-app/device integration. Bonsai-27B locally and an Alibaba cloud API are **candidates to evaluate later**, only after their phase and budget are approved.

The repository is private during review. Challenge judges need a GitHub invitation to inspect the code; a link alone does not grant access.
