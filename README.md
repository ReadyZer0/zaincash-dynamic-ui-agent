# READY — Iraqi Arabic payment companion

**Agentic AI Challenge Iraq · Topic 04: Bill Pay & Transfer Agent**

READY turns a short Iraqi Arabic request into a clear payment review, an explicitly confirmed **mock** transaction, and a result the user can check. Dynamic UI brings the relevant control into the conversation. Transparent risk coaching, traceable wallet figures and a support draft help before and after the payment.

This is an independent prototype, not an official ZainCash application or integration. All users, balances, contacts, bills and transactions are fictional. **No real money moves.** A real model can interpret requests when configured; it cannot confirm a payment or change the signed-in demo account.

## Start the app

Python 3.12+ is recommended; no third-party Python runtime packages are required.

```bash
python server.py
```

On Windows, `py -3 server.py` also works. Open `http://127.0.0.1:8765` on the same computer. The default is `OFFLINE_DEMO`, a deterministic interpreter with no model calls. Select a fictional profile and try `حول ٥٠ ألف لعلي`: the app asks which saved Ali you mean before preparing a review.

The server creates `data/demo_wallet.sqlite3`. To use a fresh, separate dataset, set `READY_DB_PATH` to a new local file before starting. Existing balances are preserved on restart. Do not put real data into it.

### Connect a real model

Follow [LLM_SETUP.md](docs/LLM_SETUP.md) for Windows/Linux commands with a hidden API-key prompt. Configure these on the **backend**:

| Setting | Purpose |
| --- | --- |
| `READY_AGENT_MODE=llm` | Explicitly enable model calls |
| `READY_LLM_BASE_URL` | Provider's OpenAI-compatible base URL |
| `READY_LLM_MODEL` | Exact enabled model with function/tool calling |
| `READY_LLM_API_KEY` | Server-side credential, never bundled in the APK |

**Gemini Flash is the initial planned provider**, using Google's OpenAI-compatible endpoint. Use the exact enabled model from AI Studio; [LLM_SETUP.md](docs/LLM_SETUP.md) has the current example and hidden-key commands. The adapter preserves Google's current-turn tool-call thought signatures and has scripted compatibility tests. No live Gemini dialect/quality result is claimed yet. Local compatible loopback model servers are also supported. The app distinguishes configuration present from a successful model request. A failed call never silently becomes an offline result. `.env` files are not loaded automatically.

### Android APK

The native **READY Demo** client loads the same mobile interface from this backend. It contains neither Python nor an LLM key. The backend computer must remain available while testing.

See [ANDROID.md](docs/ANDROID.md) for APK metadata, installation, USB setup, limitations and a source rebuild. With Android platform tools and USB debugging ready, run on the backend computer:

```bash
adb reverse tcp:8765 tcp:8765
```

```bash
adb install -r AliDheaa_Topic04_READY_Debug.apk
```

Open READY Demo and connect to its default `http://127.0.0.1:8765/`. The server remains loopback-only; entering a LAN address or public URL does not enable remote hosting. The advanced HTTPS setting requires a separately secured deployment, which is not included here.

## Implemented features

- Iraqi Arabic/RTL chat, large-text option, mobile review and registered Dynamic UI actions shared by chat and menus.
- Explicit offline mode plus a bounded real-model tool loop: current contacts, bills, balance/history, clarification, one prepared review, status, insights and support draft. Bounds: 4 provider rounds, 8 tool calls and a 45-second turn budget.
- Closed tool schemas; current owner-scoped lookups; conservative recipient, bill and amount grounding. Unsupported wording asks for clarification rather than inventing a draft.
- Server-owned draft version, owner/session binding, expiring HttpOnly approval credential, CSRF checks, final Confirm, transactional idempotency and receipt recovery. Chat text cannot confirm a payment.
- Readable advisory risk rules before confirmation and estimated remaining balance. These are prototype heuristics, not a measured fraud classifier.
- Wallet summaries calculated from source records with references and explicit limits. Illustrative history is not a cash-flow forecast or profit figure.
- Owner-scoped support draft using the original transaction. The user reviews/copies it. **No message is sent and no external support ticket is created.**
- Monthly reminder/preparation configuration with separate review: no timer, notification or automatic debit.
- Native Java Android shell: selected-origin WebView, loopback-only cleartext, certificate errors fail closed, no native JavaScript bridge or shared provider key.

## Evaluation and tests

```bash
python -m unittest discover -s tests -v
```

The original 24-test baseline was rerun successfully before changes. The expanded suite covers the wallet, HTTP boundary, scripted model protocol, multi-turn integration, recovery/advisory failures and evaluator correctness. See the dated [implementation status](docs/IMPLEMENTATION_STATUS.md).

```bash
python -m evaluation.run --mode offline
```

On 21 October 2026, the offline development run passed **74/74 cases and 80/80 turns**, with **0 incorrect proposals and 0 ledger changes during chat**. These AI-authored cases informed implementation fixes. They are **not held out or native-human reviewed**. This is not real-model accuracy or payment completion accuracy: the evaluator never presses Confirm. Confirmation and retry behavior have separate tests.

See [the final measured report](docs/evaluation-results/20261021_offline_final.md) and [evaluation protocol](docs/EVALUATION.md). Live evaluation requires explicit network opt-in and can consume quota. No live provider call, real-model latency/cost, or physical Android device test is claimed in this delivery.

### Iraqi-Arabic test pack — 22 October

The [new test and prompt guide](docs/IRAQI_TEST_HARNESS.md) adds **200 runnable development cases** (224 turns), **60 detailed scenario specifications**, **10 executable mock payment workflows** and **four versioned prompts**. The [official ZainCash feature matrix](docs/ZAINCASH_FEATURES.md) grounds the realistic service requests in official documentation and identifies what the prototype can actually execute.

The full local automated suite passed **102 tests**. The new Iraqi cases passed **187/200 cases and 211/224 turns**, revealing **13 failures, including six incorrect payment reviews**, with zero committed ledger mutations during chat. Negated amounts, bill scope and requested wallet provider need fixes before payment readiness can be claimed. See the [failure backlog](docs/IRAQI_TEST_HARNESS.md#first-findings-and-required-fixes); passing the older 74 cases does not erase these misses. The 60 richer scenarios remain specifications requiring execution/review, and no set is native-human-reviewed or held out.

The [22 October evidence summary](docs/evaluation-results/20261022_harness_summary.md) links the complete JSON/Markdown reports from clean implementation commit `6fe565e`, including **10/10 mock workflows with 270 assertions** and the retained 74/74 baseline.

```bash
python -m evaluation.run --mode offline --cases evaluation/iraqi_v1/cases.jsonl
```

```bash
python -m evaluation.flow_scenarios --output-dir evaluation/results
```

## Focus and roadmap

The [full build plan](docs/BUILD_PLAN.md), committed before implementation, keeps the project focused on Topic 04. It brings useful parts of Topic 01 (risk coaching), Topic 02 (traceable wallet context), and Topic 06 (recovery information) into the payment journey. These helpers are not complete submissions for those other topics. Loan-file preparation and synthetic document capture remain gated later work.

Before the 8 November MVP: connect and benchmark an actual model, have Iraqi speakers edit at least 50 dialect requests, observe users completing payment and recovery tasks, freeze a fresh final set and measure it without tuning on its answers. Planned targets remain targets, not achieved held-out results.

## Intended failure behavior and current boundaries

These controls are the intended contract. The new Iraqi development run exposes interpretation gaps before review creation; consult the [dated failure backlog](docs/IRAQI_TEST_HARNESS.md#first-findings-and-required-fixes) when assessing the rows below.

| Situation | Behavior |
| --- | --- |
| Duplicate name, missing amount or unsupported currency | Ask for clarification; never guess a payment |
| Model timeout/authentication/quota failure | Explicit error; no disguised offline fallback; menus remain available |
| Negative/decimal/malformed amount, negated or multiple payments | Conservative clarification/refusal before preparation |
| Changed, expired or superseded review | Reject old approval; require a fresh review |
| Repeated final confirmation | Return stored receipt; one mock debit |
| Unknown payment result | Query the original record; do not create another payment automatically |
| Optional advisory log unavailable after debit | Preserve the authoritative receipt and disclose the advisory failure |
| Another user's transaction/support reference | Owner-scoped lookup rejects it |

Demo sessions are not production authentication. Real customer data, official payment adapters, production KYC, credit decisions and public hosting are outside this release. Natural-language guards are conservative and do not prove perfect interpretation of arbitrary paraphrases. The readable review and separate server confirmation remain essential.

## Architecture, data and disclosure

- [Architecture](docs/ARCHITECTURE.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Synthetic fixture data](docs/DEMO_DATA.md)
- [Full plan and week-by-week roadmap](docs/BUILD_PLAN.md)
- [Android setup/build](docs/ANDROID.md)
- [Model connection](docs/LLM_SETUP.md)

OpenAI ChatGPT and coding agents assisted planning, implementation, tests and synthetic case authoring. The runtime inference model is a separate configurable choice and must be disclosed with each live evaluation. No competitor code was copied. Keys, databases, APK signing material and downloaded build tools are excluded from Git.
