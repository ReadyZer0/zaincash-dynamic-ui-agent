# Implementation and verification — 21 October 2026

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
