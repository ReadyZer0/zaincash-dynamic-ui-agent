# Windows continuation — 22 October 2026 (Asia/Baghdad)

Starting point: PR #1, open/draft/unmerged, head `4eae03bf40a1f9bc4c3c175dfc118a442a14a710`. Fresh isolated checkout on `feat/windows-continuation`; the pre-existing project mirror and its unfinished edits remain untouched.

## This increment

- [x] Fetch the implementation branch and verify the three supplied commits.
- [x] Read the committed plan, implementation, architecture, model/Android and evaluation documents.
- [x] Run baseline suite and offline evaluator on Windows. Both revealed open SQLite handles blocking temporary database cleanup; do not reuse the historical 76/76 claim as this machine's result.
- [x] Close SQLite resources deterministically without weakening transactions or cleanup assertions. The Windows regression suite and offline evaluator now complete.
- [x] Provide a small foreground launcher/preflight with explicit offline default and hidden, transient model-key entry. No secret is accepted in arguments or files; offline mode makes no model calls.
- [x] Rebuild Android from current source with a project-local official JDK/SDK. The build verifies package/version/API, endpoint policy, signature, alignment and DEX; physical-device runtime remains unverified.
- [x] Align evaluation documentation on 5–8 observed sessions; provide reviewer templates and a frozen-dataset validation workflow. No participants or held-out results are invented.
- [ ] Run fresh narrow/wide browser workflows against a disposable synthetic database and inspect screenshots. The in-app browser's URL security gate denied the loopback tab; do not bypass that gate with another browser route. Source/API tests ran, but fresh visual verification remains open.
- [x] Update current-versus-planned evidence, brief/demo material and setup docs. The original historical report and deck remain intact.
- [ ] Commit meaningful changes and publish a reviewable continuation branch/PR; do not merge PR #1.

## External inputs / gates

- Provider selection remains deferred by the user. Exact tool-capable model, endpoint, secure key entry and bounded quota approval are needed before live smoke evaluation; no live result may be fabricated.
- Android installation/runtime needs an available authorized phone/emulator. Never silently uninstall an existing differently signed app.
- At least 50 Iraqi-speaker edits and 5–8 task-based sessions need actual participants. New final 200 dialogues must be reviewed and frozen separately from development examples.
- No hackathon-form submission, organizer message, real payment, public backend deployment or external notification is part of this continuation.

## Preserved older local work

The parent project mirror contains unfinished saved-schedule/monthly-history and development-corpus edits from before the PR handoff. They were not copied over the newer implementation. Reconcile useful changes in a separate tested increment after this continuation; do not silently drop or overwrite them.
