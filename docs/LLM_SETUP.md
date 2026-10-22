# Connect a model to READY

READY keeps the model API credential on the Python backend. The Android APK is
a client of that backend; it contains neither the provider key nor a Python
server. All wallet records and payments remain synthetic when a real model is
connected. A model key does not enable real ZainCash transfers.

The default is **offline**. Live model mode uses an OpenAI-compatible Chat
Completions endpoint with function/tool calling. This adapter has been tested
against scripted responses and a loopback fake HTTP provider. A first bounded
Gemini cloud attempt returned a provider HTTP error, so no successful model
turn, dialect accuracy, or actual token cost is claimed.

## Choose the endpoint and model

### Gemini trial preset (prepared 22 October 2026)

READY's Gemini preset uses Google's [OpenAI-compatible Chat Completions endpoint](https://ai.google.dev/gemini-api/docs/openai/)
at `https://generativelanguage.googleapis.com/v1beta/openai` with the
tool-capable `gemini-3.8-flash` model. Google's [function-calling example](https://ai.google.dev/gemini-api/docs/openai/)
uses this model and endpoint. The adapter returns Gemini's opaque tool-call
thought signature only within the transient provider conversation, as required
for multi-step calls; it never enters wallet tools, UI traces or saved chat.
This is a compatibility implementation, **not a successful live-model test**.
The first synthetic one-case smoke on 22 October 2026 failed with a provider
HTTP error and zero ledger changes; [the sanitized report](evaluation-results/20261022_gemini_smoke1.md)
records the result. The response body was not logged. The adapter now sends
only the documented function-schema subset, and retains backend validation of
all model actions. That revision has passed local tests but has not yet passed
a live smoke.

After confirming that the key belongs to a **free-tier** project in Google AI
Studio, rotate any credential shared in chat and enter the replacement only
through the hidden local prompt. Do not place it in a file, command argument,
repository, screenshot, mobile chat or message to Codex. Run **one** bounded
synthetic smoke process from this checkout:

```powershell
py -3 scripts/ready.py smoke --mode llm --provider gemini --allow-network --limit 1
```

On this Windows host, `py` is not on `PATH`; use the bundled Python executable
instead: `& 'C:\Users\Ready\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/ready.py smoke --mode llm --provider gemini --allow-network --limit 1`.
Run it from the repository folder in your own PowerShell so the masked prompt
is visible. Do not send the key through chat. The first provider attempt used
one of the five approved requests; at most four remain under that approval.

The preset requires explicit live mode and network opt-in. It has a hard cap of
**five outbound provider attempts per process**, counting failures; one case
can require multiple attempts. The cap resets if the process restarts, so it is
not an account-level spending control. Do not repeat the command or start a
live server under a five-request approval without reviewing the prior usage.
The app remains offline by default. Google's [pricing page](https://ai.google.dev/gemini-api/docs/pricing)
lists free-tier access for this model, but a request cap cannot prove which
billing tier your specific key uses. Use synthetic data only: Google states
free-tier content may be used to improve its products. No real wallet record,
payment credential or customer data is suitable for this trial.

If the smoke result is satisfactory and a separate running-session budget is
approved, `py -3 scripts/ready.py serve --mode llm --provider gemini --allow-network`
starts the app with another hidden key prompt. The server still cannot let the
model confirm or commit a payment; the final Confirm remains server-owned.

### Other compatible providers

Obtain the exact base URL, model ID and credential from your provider's console.
Choose a model that supports Chat Completions **function calling**. An ordinary
text-only completion endpoint is insufficient.

For Alibaba Cloud Model Studio, the current official API documentation lists
workspace-specific regional domains. A Singapore example is:

```text
https://YOUR_WORKSPACE_ID.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
```

This is a template, not a working account. Use the endpoint for your own
workspace and region. The provider documents the older DashScope domains as
still functional; check which endpoint and models your account enables. READY
appends `/chat/completions` to the configured base URL.

Primary references, checked 21 October 2026:

- [Alibaba OpenAI-compatible Chat API](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions)
- [Alibaba function calling](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen-function-calling)
- [Alibaba API-key setup](https://www.alibabacloud.com/help/en/model-studio/get-api-key)

Do not paste your API key into ChatGPT, a repository file, the mobile chat, a
screenshot or the APK. The commands below ask for the key through a hidden
terminal prompt and keep it in the running backend process environment.

## Start on Windows PowerShell

The repository also has a foreground launcher. It checks Python, SQLite and
Baghdad timezone data, defaults to the offline mode, and requires an explicit
network opt-in for live mode:

```powershell
py -3 scripts/ready.py check
py -3 scripts/ready.py serve
```

After you have selected a provider and confirmed its quota, set the public URL
and exact tool-capable model ID shown below. Then run:

```powershell
py -3 scripts/ready.py serve --mode llm --allow-network
```

The launcher uses a hidden prompt for the key; it neither writes an `.env` file
nor puts the key in the command line or APK. It rejects an endpoint that already
ends in `/chat/completions`. The preflight explains how to add `tzdata` if the
Windows Python installation has no IANA timezone database. Starting the server
still requires a separate provider choice and an approved quota budget.

Run each line in the repository folder, in the same PowerShell window. Replace
the endpoint and model placeholders with the values from your provider.

```powershell
$env:READY_AGENT_MODE="llm"
$env:READY_LLM_BASE_URL="https://YOUR_WORKSPACE_ID.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
$env:READY_LLM_MODEL="YOUR_ENABLED_TOOL_CAPABLE_MODEL"
py -3 -c "import getpass,os,runpy; os.environ['READY_LLM_API_KEY']=getpass.getpass('Backend model API key: '); runpy.run_path('server.py',run_name='__main__')"
```

If your Python executable is named `python`, replace `py -3` with `python`.
The environment settings apply to this terminal session. Stop the server with
Ctrl+C; restarting it requires entering the credential again.

## Start on macOS or Linux

```bash
export READY_AGENT_MODE=llm
export READY_LLM_BASE_URL=https://YOUR_WORKSPACE_ID.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
export READY_LLM_MODEL=YOUR_ENABLED_TOOL_CAPABLE_MODEL
python -c "import getpass,os,runpy; os.environ['READY_LLM_API_KEY']=getpass.getpass('Backend model API key: '); runpy.run_path('server.py',run_name='__main__')"
```

Use `python3` if that is your Python 3 command. No third-party Python runtime
package or OpenAI SDK is required by this adapter. The project does not load
`.env` files automatically.

## Optional provider-specific setting

Some Qwen models offer a thinking switch. If your selected model documents
`enable_thinking`, setting `READY_LLM_ENABLE_THINKING=false` adds that exact
request property. Leaving it unset omits the property for broader provider
compatibility. Do not send it to a provider that rejects this option.

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
- This remains a local mock prototype with demo sessions. It is not ready for
  public hosting, real customer data or real payment integration.
