# Connect a model to READY

READY keeps the model API credential on the Python backend. The Android APK is
a client of that backend; it contains neither the provider key nor a Python
server. All wallet records and payments remain synthetic when a real model is
connected. A model key does not enable real ZainCash transfers.

The default is **offline**. Live model mode uses an OpenAI-compatible Chat
Completions endpoint with function/tool calling. This adapter has been tested
against scripted responses and a loopback fake HTTP provider. No actual cloud
model, dialect accuracy, inference cost or cloud latency is claimed as tested
until an authorized key and selected model are used.

## Initial provider: Gemini Flash

Gemini Flash is the project's initial planned model provider. Google's official
OpenAI-compatible Chat Completions endpoint is:

```text
https://generativelanguage.googleapis.com/v1beta/openai
```

Google's documentation checked on **22 October 2026** uses
`gemini-3.8-flash`. Use the exact Flash model enabled in your own AI Studio
project if that example is unavailable; model IDs, free-tier eligibility and
quotas can change. READY appends `/chat/completions` to the base URL. A model
must support function calling; text-only completion is insufficient.

The adapter preserves validated `extra_content.google.thought_signature`
metadata on assistant tool calls within the current turn. Scripted tests check
that the original signature reaches the next provider request and is absent
from public output. This is protocol evidence, not proof that a real Gemini
request or Iraqi-Arabic task has succeeded. Conversation history does not retain
a full cross-turn provider transcript; test multi-turn behavior with the exact
chosen model.

Primary references, checked 22 October 2026:

- [Google OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)
- [Google thought signatures](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures)
- [Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key)

Do not paste your API key into ChatGPT, a repository file, the mobile chat, a
screenshot or the APK. The commands below ask for the key through a hidden
terminal prompt and keep it in the running backend process environment.

## Start on Windows PowerShell

Run each line in the repository folder, in the same PowerShell window. Replace
the model example if your AI Studio project enables a different Flash model.

```powershell
$env:READY_AGENT_MODE="llm"
$env:READY_LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
$env:READY_LLM_MODEL="gemini-3.8-flash"
Remove-Item Env:READY_LLM_ENABLE_THINKING -ErrorAction SilentlyContinue
py -3 -c "import getpass,os,runpy; os.environ['READY_LLM_API_KEY']=getpass.getpass('Backend model API key: '); runpy.run_path('server.py',run_name='__main__')"
```

If your Python executable is named `python`, replace `py -3` with `python`.
The environment settings apply to this terminal session. Stop the server with
Ctrl+C; restarting it requires entering the credential again.

## Start on macOS or Linux

```bash
export READY_AGENT_MODE=llm
export READY_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
export READY_LLM_MODEL=gemini-3.8-flash
unset READY_LLM_ENABLE_THINKING
python -c "import getpass,os,runpy; os.environ['READY_LLM_API_KEY']=getpass.getpass('Backend model API key: '); runpy.run_path('server.py',run_name='__main__')"
```

Use `python3` if that is your Python 3 command. No third-party Python runtime
package or OpenAI SDK is required by this adapter. The project does not load
`.env` files automatically.

## Optional provider-specific setting

Some Qwen models offer a thinking switch. If your selected model documents
`enable_thinking`, setting `READY_LLM_ENABLE_THINKING=false` adds that exact
request property. Leaving it unset omits the property for broader provider
compatibility. Leave it unset for Gemini: this Qwen-specific property does not
select Google's thinking settings. Other compatible providers remain configurable;
obtain their exact endpoint and tool-capable model from their official console.

For a local compatible model server, an explicit literal loopback HTTP base URL
such as `http://127.0.0.1:8000/v1` is allowed. A key is optional for that local
case. Remote providers require HTTPS and a backend key. Model quality, local
hardware requirements and tool-call support still need separate validation.

## Check the connection and agent behavior

Open `http://127.0.0.1:8765` on the backend computer. For the Android APK, follow
[the Android connection instructions](ANDROID.md), including USB port reverse.
The backend remains loopback-only; a phone on the same Wi-Fi cannot connect
directly to the computer's LAN address.

The app distinguishes configured mode from a successful model request. Merely
seeing a configured model ID is not proof that the key or provider works.

Try these synthetic tasks:

1. `شكد رصيدي؟` — the model should read the balance and show a server-owned card.
2. `حول ٥٠ ألف لعلي` — the assistant should ask which saved Ali you mean.
3. Reply `علي ضياء` — it should look up current contacts, prepare the selected
   50,000 IQD transfer and show a review. The balance must remain unchanged.
4. Type `نعم` — text alone must not execute. Use the separate final Confirm
   control only after checking the review.
5. Request a water bill on a profile with only an electricity bill — the model
   must not substitute the electricity bill.
6. Ask for wallet insights or help with a known transaction — the data should
   have source references; a support draft must say it has not been sent.

Tool activity records tool names, outcomes and elapsed time. It does not expose
hidden model reasoning, provider credentials, HTTP bodies, confirmation tokens
or raw session state. The server's cards and receipts are authoritative; model
prose is an explanation, not proof that money moved.

Provider authentication failures, rate limits, timeout and invalid tool output
produce explicit errors. There is no automatic switch to the offline router
while pretending the model succeeded. You may deliberately use the ordinary
menu controls or restart in offline mode.

## Offline mode and testing

To return to the deterministic demo, set `READY_AGENT_MODE=offline` and start
`python server.py` (or `py -3 server.py` on Windows). No model request is made.

Run the automated suite:

```bash
python -m unittest discover -s tests -v
```

The model adapter tests use scripted model messages and a temporary loopback
fake provider. They verify closed tools, exact argument schemas, no commit
capability, owner-record lookup, ambiguity handling, safe transport, budget
limits and secret exclusion. They do **not** measure a real model's language
understanding. Run the separate development evaluator after connecting your
chosen model, and record provider/model, code revision, case-set hash, successes,
misses and latency. Human Iraqi-Arabic review and a held-out final set are still
required for the competition evidence.

The offline evaluation does not call a provider even if a key is present:

```bash
python -m evaluation.run --mode offline
```

For a first live smoke evaluation, use a fresh terminal with the same model and
endpoint environment variables. The following command prompts for the key and
explicitly enables network calls for only the first five development cases:

```bash
python -c "import getpass,os,runpy,sys; os.environ['READY_LLM_API_KEY']=getpass.getpass('Backend model API key: '); sys.argv=['evaluation.run','--mode','llm','--allow-network','--limit','5']; runpy.run_module('evaluation.run',run_name='__main__')"
```

On Windows replace `python` with `py -3` if needed. A live evaluation can consume
provider quota; the five-case limit is a smoke check, not the full result. See
[the evaluation guide](EVALUATION.md) for selected cases, full runs and reporting.

## Bounds and known tradeoffs

- At most 4 provider calls and 8 tool calls per chat turn, with a 45-second run
  budget and a 20-second provider-call timeout. A slow or incompatible model
  fails visibly; the app does not increase its budget silently.
- One prepared payment per turn. A prepare/clarification cannot be batched with
  other model calls in the same tool batch. No automatic payment retries.
- The model must look up current contacts/bills before preparing. Contact
  identity must be supported by user words; a previous assistant assertion is
  not sufficient. Common bill categories are checked against the selected saved
  bill; unusual wording can cause an extra clarification rather than a guess.
- Transfer amounts must exactly match the shared deterministic amount parser's
  result from the current user request or a later user clarification. A model
  cannot invent a missing amount, multiply a bare `50`, or replace `50,000` with
  `5,000`. Unrecognized written amounts and multiple numeric values ask for an
  explicit amount. This conservative check trades some linguistic flexibility
  for a review whose amount has direct user evidence.
- Model explanations always carry a canonical notice that they do not execute
  payment. Obvious unsupported success claims are replaced; this is a heuristic,
  not a proof about every possible phrasing. A real server receipt/status card
  remains the authoritative evidence of a mock payment.
- History stores at most six short user/assistant messages and roughly 2,700
  JSON characters per demo session. Tool results exist only in the current
  model turn. Long conversations can require the user to repeat details.
- Provider compatibility and model intelligence are separate from the wallet's
  confirmation boundary. Tests of one do not prove the other is perfect.
- Use only synthetic inputs for live evaluation. The app's current scrubbing
  and public-response echo checks do not guarantee removal of arbitrary PIN/OTP
  text pasted by a user before it reaches a provider request. The detailed
  scenario catalog records stronger ingress protection as an unexecuted target.
- This remains a local mock prototype with demo sessions. It is not ready for
  public hosting, real customer data or real payment integration.
