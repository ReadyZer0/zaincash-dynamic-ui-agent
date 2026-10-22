# Implementation and verification — 21 October 2026

## Windows continuation — 22 October 2026 (Asia/Baghdad)

This section reports the **new** Windows continuation of draft PR #1 on
`feat/windows-continuation`. The dated 21 October report below remains historical
evidence for its own source revision; it is not a current test result.

The current Python suite passed **104/104** tests on Windows, including live
loopback HTTP tests, deterministic SQLite cleanup, owner/review/confirmation
regressions, local launcher boundaries, final-set validation scaffolding and
Android build safety. The offline **development** evaluator passed 74/74 cases
and 80/80 turns with zero wrong payment proposals and zero chat-triggered ledger
changes. Those cases remain AI-authored development data; no live model,
held-out set or human reviewer was involved. Tests used synthetic local data.

The Android APK was rebuilt locally on 22 October using Temurin JDK 17.0.20.1,
Android platform 35 and Build Tools 35.0.0. Endpoint policy passed 38 checks;
the build verified package/version/API, APK ZIP and DEX integrity, 16-KiB
alignment, and v2/v3 signing. The generated `android/build/outputs/build-info.json`
records the actual build source fingerprint, size and SHA-256. No phone or
emulator was available, so install/launch and real device usability have **not**
been verified. The APK is a debug client that still requires the local backend.

`scripts/ready.py check`, Python compilation, JavaScript syntax and
`git diff --check` passed. The RTK/Ruff lifecycle guard refused to run Ruff
from this isolated clone; no Ruff result is claimed. A fresh browser visual
check was not possible: the in-app browser denied the loopback URL via its
security policy, so no alternate browser route was used. Historical browser
observations below are retained with their original date, not repeated here.

The five-slide build-stage brief now separates these development checks from
planned 200-dialogue, 50 Iraqi-speaker-edit and 5–8 usability-session targets.
Provider selection, live-model requests, held-out evaluation and device
inspection remain future gates. No hackathon form was submitted.

## Published implementation — 21 October 2026

The full plan was recorded in `docs/BUILD_PLAN.md` and committed before this
implementation increment. This delivery implements the initial connected mobile
prototype, not every item on the roadmap to 8 November.

## Completed

- Optional real-model provider connection and bounded tool loop; explicit
  offline default; strict tool/argument validation and safe provider failures.
- Multi-turn clarification with current owner-scoped lookup and user-grounded
  contact, bill and amount checks. No confirmation/debit tool exists.
- Advisory risk explanations, exact remaining-balance arithmetic, source-linked
  wallet summary and unsent support draft for the original transaction.
- Iraqi Arabic mobile review, visible mode/tool activity, amount in the final
  confirmation control, balance refresh, status/support recovery and large text.
- Android client source, reproducible SDK build script and signed debug APK.
- Development dataset, evaluator, test coverage and dated machine-readable
  results. Model/setup/architecture/threat/data documentation updated.

## Verification performed

The final offline evaluation was rerun on clean published implementation commit
`157c46a5bbb647160702089f43a2849e5819eff3`. Its [Markdown report](evaluation-results/20261021_offline_final.md)
and [machine-readable observations](evaluation-results/20261021_offline_final.json)
record the source revision, application fingerprint and dataset hash. The earlier
development report is retained separately.

| Check | Observed result | What it establishes |
| --- | --- | --- |
| Original repository baseline | 24/24 tests passed before changes | Starting local HTTP/wallet behavior |
| Expanded Python suite | 76/76 tests passed | HTTP wallet regressions, scripted model protocol, integrated multi-turn preparation/confirmation, advisory failure isolation and evaluator correctness |
| Offline development evaluation | 74/74 cases, 80/80 turns; 0 wrong proposals; 0 ledger changes during chat | Regression behavior on AI-authored cases used during development; not held-out or real-model quality |
| Android endpoint policy | 38 assertions passed | Scheme/origin/port restrictions and malformed endpoint rejection |
| APK structure and signing | Manifest, DEX, alignment and v2/v3 signature verified | A compiled signed debug artifact; not proof of physical-device execution |
| Browser workflow | Passed at 390×844 mobile and 1280×900 desktop viewports | Ambiguous contact → review → typed yes has no debit → explicit Confirm → balance update/receipt → unsent support draft → source-linked insights |
| Browser layout/runtime | No horizontal overflow or JavaScript page errors in the exercised workflow; screenshots visually inspected | The tested responsive browser flow only, not every Android keyboard/device behavior |
| Source checks | Python compilation, JavaScript syntax and whitespace checks passed | Basic package/source validity |

Model protocol tests use scripted messages and a temporary loopback fake HTTP
provider, not an actual commercial model. The optional browser smoke script is
`tests/ui_smoke.cjs`; it needs Playwright and a Chrome executable and performs
one synthetic 50,000 IQD payment against a fresh running local backend. It is
not part of the Python-only setup and must never target real financial data.

## APK

Filename: `AliDheaa_Topic04_READY_Debug.apk`

- Package: `iq.ready.billpay.demo`
- Version: `0.2.0-demo`; minimum Android 8.0 / API 26; target API 35
- Size: 33,326 bytes
- SHA-256: `da8a3bad93324b595bb238d02f0db42a8d91a45796dd71168b804e9f1efd6550`
- Build: Java 17.0.20, Android platform 35, Build Tools 35.0.0
- Only requested permission: `INTERNET`
- No provider API key, Python server or model bundled

The APK connects to the Python backend. USB `adb reverse` is the supported
initial device route. Installation alone does not provide an offline wallet
server or a hosted service. See [Android instructions](ANDROID.md).

## Concrete issues found and fixed

The starting router could prepare a positive amount from a negative input,
prepare on a negated request, silently ignore the second payment in a compound
request, and substitute a saved electricity bill for an unknown bill. New
regression cases cover these, common written amounts, malformed separators,
confirmation-bypass text and account-switch text.

A scripted model initially could choose a known contact from an ambiguous name
or supply an invented/mismatched amount. The adapter now rejects those tool
requests before dispatch. Advisory writes after commit were isolated so an
optional risk log failure cannot hide an authoritative receipt. Cancellation
records the reviewed version's risk reasons. Historical display prefixes no
longer cause a known fixture recipient to be incorrectly flagged as new.

## Still unmeasured or planned

- Actual provider compatibility and live agent behavior with an authorized API
  key, including Iraqi Arabic quality, latency, token cost and rate limits.
- APK installation and runtime behavior on the user's physical Android phone;
  no phone or Android emulator was available here.
- At least 50 dialect cases edited by Iraqi speakers, 5–8 observed usability
  sessions and a fresh frozen final evaluation. No interviews or human ratings
  are invented.
- Voice, synthetic document capture/KYC completeness, merchant cash-flow
  projection and loan-file preparation remain gated later work.
- Production authentication, public hosting and real payment integration are
  outside this prototype. The API key activates model interpretation only.

No hackathon form was submitted as part of this implementation.
