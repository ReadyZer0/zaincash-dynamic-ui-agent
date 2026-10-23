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

For a foreground setup check and explicit model launch, use the standard-library helper:

```powershell
py -3 scripts/ready.py check
py -3 scripts/ready.py serve
```

`serve` defaults to offline mode. A live-model launch requires separate provider/quota approval and explicit `--mode llm --allow-network`; do **not** start it under the current uncertain Gemini trial allowance. It prompts for a backend-only key if none is saved. See [model setup](docs/LLM_SETUP.md). On Windows, the preflight reports missing Baghdad timezone data with an install command; it does not install packages automatically.

The server creates `data/demo_wallet.sqlite3`. To use a fresh, separate dataset, set `READY_DB_PATH` to a new local file before starting. Existing balances are preserved on restart. Do not put real data into it.

### Connect a real model

Follow [LLM_SETUP.md](docs/LLM_SETUP.md) for Windows/Linux commands with a hidden API-key prompt. Configure these on the **backend**:

| Setting | Purpose |
| --- | --- |
| `READY_AGENT_MODE=llm` | Explicitly enable model calls |
| `READY_LLM_BASE_URL` | Provider's OpenAI-compatible base URL |
| `READY_LLM_MODEL` | Exact enabled model with function/tool calling |
| `READY_LLM_API_KEY` | Server-side credential, never bundled in the APK |

Use the actual endpoint/model from the provider console. Alibaba Qwen's compatible API is a documented candidate; no specific cloud model quality or compatibility result is claimed yet. Local compatible loopback model servers are supported. The app distinguishes configuration present from a successful model request. A failed call never silently becomes an offline result. `.env` files are not loaded automatically.

A Gemini trial preset is now available through `scripts/ready.py` with a hidden
key prompt, an optional backend-only Windows Credential Manager setting, and a
five-outbound-request process cap. It remains **off** unless
`--mode llm --provider gemini --allow-network` is supplied. See
[Gemini setup and key rotation](docs/LLM_SETUP.md#gemini-trial-preset-prepared-22-october-2026).
The first synthetic Gemini smoke failed with a provider HTTP error. A later
one-case smoke on 23 October failed with `MODEL_TIMEOUT` (**0/1**, zero ledger
changes); [the report](docs/evaluation-results/20261023_gemini_smoke2.md)
predates per-run request counting, so the total spent from the five approved
requests is uncertain. No further live requests are being made under that
approval. The exposed chat key was not reused. A saved-key setting alone does
not call a model or enable payments.

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

See [the final measured report](docs/evaluation-results/20261021_offline_final.md) and [evaluation protocol](docs/EVALUATION.md). Live evaluation requires explicit network opt-in and can consume quota. That dated 21 October run involved no live provider call or physical Android device test.

The 22 October continuation from draft [PR #1](https://github.com/ReadyZer0/zaincash-dynamic-ui-agent/pull/1) is tracked in [its checklist](docs/CONTINUATION_CHECKLIST.md). Its clean-source Windows suite passed **104/104**, and its clean-source offline **development** run passed **74/74 cases, 80/80 turns**; see [current status](docs/IMPLEMENTATION_STATUS.md) and the [dated report](docs/evaluation-results/20261022_windows_offline.md). After the later Gemini preparation, the expanded suite passed **110/110** and a [new clean-source offline development run](docs/evaluation-results/20261022_gemini_prep_offline.md) passed **74/74 cases, 80/80 turns**. A first [synthetic Gemini smoke](docs/evaluation-results/20261022_gemini_smoke1.md) failed with a provider HTTP error and no ledger change; the compatibility payload was revised and retested locally. A later hidden-key retry failed before any network request; the now clearer validator passed in the expanded **111/111** local suite. No successful Gemini turn is yet claimed. The clean-source debug APK was rebuilt and structurally verified, but has not been run on a phone. The 21 October report above retains its original revision. The [human-review protocol](docs/HUMAN_REVIEW.md) prepares a separate final dataset without representing AI-authored development examples as native-speaker evidence.

## Focus and roadmap

The [full build plan](docs/BUILD_PLAN.md), committed before implementation, keeps the project focused on Topic 04. It brings useful parts of Topic 01 (risk coaching), Topic 02 (traceable wallet context), and Topic 06 (recovery information) into the payment journey. These helpers are not complete submissions for those other topics. Loan-file preparation and synthetic document capture remain gated later work.

Before the 8 November MVP: connect and benchmark an actual model, have Iraqi speakers edit at least 50 dialect requests, observe users completing payment and recovery tasks, freeze a fresh final set and measure it without tuning on its answers. Planned targets remain targets, not achieved held-out results.

## Failure behavior and boundaries

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
