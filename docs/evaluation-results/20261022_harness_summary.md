# Iraqi-Arabic harness results — 22 October 2026

**The pack is prepared and locally exercised. It exposes unresolved application
defects; it does not establish perfect behavior or live Gemini accuracy.**

The three evaluation reports below were generated from clean implementation
commit `6fe565e08c41156a37b19059721db27a783b2c2a`. This subsequent evidence commit
adds reports and documentation only. The reports preserve source and prompt
hashes and all failures without relabelling expected outcomes.

| Check | Observed result | Evidence and scope |
| --- | --- | --- |
| Complete automated suite | 102 tests passed | `python3 -m unittest discover -s tests -q`; 14.262 seconds; scripted provider and local mock/HTTP tests |
| Existing 74-case development regression | 74/74 cases, 80/80 turns | [Markdown](20261022_baseline_74.md) / [JSON](20261022_baseline_74.json); zero incorrect proposals and zero chat ledger mutations |
| New Iraqi-Arabic development cases | 187/200 cases (93.5%), 211/224 turns | [Markdown](20261022_iraqi_dev_v1.md) / [JSON](20261022_iraqi_dev_v1.json); 13 failed cases, six incorrect proposals, zero chat ledger mutations |
| Mock payment workflows | 10/10 scenarios, 270 assertions | [Markdown](20261022_mock_api_flows.md) / [JSON](20261022_mock_api_flows.json); direct handlers with separate trusted Confirm calls |
| Rich scenario catalog | 60 specifications; 46 multi-turn; 107 user messages | NOT_RUN as a catalog; requirements for future manual/model-assisted execution |
| Live Gemini / native Iraqi review / physical Android | Not run | No claims of live accuracy, model latency, cost, native-human quality or device usability |

The 102-test run used the identical Git source tree
`4fc88822d6e3b4c8d2bb64c31f2c7367eaebe15c` before publication. The three
reported development/workflow runs were then repeated on the published commit.
The unit test console result was:

```text
----------------------------------------------------------------------
Ran 102 tests in 14.262s

OK
```

Do not combine these overlapping sets into one score. The 200 new development
cases are visible to the developers and AI-authored. They are neither native
human reviewed nor held out. The 93.5% number measures exact structured
request-to-review/clarification behavior of the deterministic local interpreter.
It does not measure completed-payment success or live-model language quality.

## Six incorrect payment reviews

- **IQ-P021:** «حوّل خمسين دينار فقط لعلي محمد، مو خمسين ألف» prepares 50,000 IQD
  instead of the intended 50 IQD.
- **IQ-P065:** a bill amount enquiry prepares a payment review.
- **IQ-P066:** a 10,000 IQD partial bill request prepares the full 45,000 IQD bill.
- **IQ-P067:** current-versus-total bill wording is ignored when preparing the saved bill.
- **IQ-A057 / IQ-A058:** FastPay/AsiaPay requests prepare ordinary ZainCash mock transfers.

The other seven failures concern recipient negation, balance/support routing,
injection-related refusal relevance, merchant QR intent and card withdrawal
intent. Full messages, expected labels and observed facts are retained in the
reports. No chat turn changed any owner's committed account, transaction,
provider-result or saved-plan record.

These wrong reviews remain release blockers even though the separate trusted
Confirm boundary prevents automatic debits. The new harness is useful because
it exposes them; changing the labels to accept the wrong outcomes would destroy
that evidence. See the [prioritized fix plan](../IRAQI_TEST_HARNESS.md#first-findings-and-required-fixes).

## Evidence limits and remaining work

Reply-quality checks are conservative lexical/known-secret checks. They do not
certify factual prose, helpfulness or natural dialect. Six support-form cases
are explicit UI parity targets that the current LLM tool set cannot satisfy
directly. Provider-ingress removal of arbitrary pasted OTP/PIN text is not fully
implemented or verified. The detailed guide identifies these limits separately.

The next useful gate is a hidden-key Gemini smoke run on synthetic inputs,
followed by the critical interpretation fixes, Iraqi-speaker review and a fresh
frozen final set. The commands, prompt roles and review rubric are in
[IRAQI_TEST_HARNESS.md](../IRAQI_TEST_HARNESS.md).
