# READY repository guidance

Read [README](README.md), [build plan](docs/BUILD_PLAN.md), and [current status](docs/IMPLEMENTATION_STATUS.md) before changing behavior. See [architecture](docs/ARCHITECTURE.md), [threat model](docs/THREAT_MODEL.md), [evaluation](docs/EVALUATION.md), [model setup](docs/LLM_SETUP.md), and [Android setup](docs/ANDROID.md) for details.

Preserve Python/SQLite/static web and the native Java client. Keep all wallet data synthetic and offline mode the default. Model tools may read, clarify or prepare only. Backend session ownership, policy, balance, review expiry/version, final UI Confirm and idempotency remain independent of model output. Never expose approval/session credentials to model context or store a provider key in source, logs, or APKs.

Use fresh databases for payment tests. Run relevant tests and record dated evidence, source revision and limitations; development cases are not held out or human-reviewed. Keep old reports intact. Do not enable real payments, external notifications, production KYC or public demo hosting. Live-model calls need approved provider/quota and securely entered credentials. Stop task-created preview servers when finished. Preserve unrelated changes and never merge PRs automatically.
