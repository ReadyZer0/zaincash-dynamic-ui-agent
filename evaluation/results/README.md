# Evaluation outputs

Run `python -m evaluation.run --mode offline` to write a timestamped JSON report
and a readable Markdown report here. Generated reports are ignored by default;
promote a deliberately reviewed report with `git add -f` when publishing dated
evidence. Never replace a failed result with a hand-edited success rate.

The bundled cases are a development set. No run on these cases is a held-out
result, and this harness does not confirm or execute payments.
