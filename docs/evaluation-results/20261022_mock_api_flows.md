# Mock API workflow scenario results

Deterministic mock API-handler workflows with separate trusted Confirm calls. No live model, browser, HTTP/CSRF/cookie, Android, or real-payment validation is claimed. Iraqi-Arabic inputs are AI-authored development fixtures, not a human-reviewed or held-out dialect evaluation.

Run (UTC): 2026-10-22T09:09:32.062539+00:00

Passed: 10/10

| Scenario | Iraqi-Arabic journey | Result | Duration (ms) |
|---|---|---|---:|
| WF001 | اختيار علي الصحيح ثم تأكيد التحويل | PASS | 59.07 |
| WF002 | فاتورة حسن ومراجعتها وتأكيدها | PASS | 47.27 |
| WF003 | كلمة كمل ما تنفذ التحويل | PASS | 56.44 |
| WF004 | الإلغاء يبطل التأكيد القديم | PASS | 60.41 |
| WF005 | تغيير المبلغ يحتاج مراجعة وتأكيد جديد | PASS | 58.46 |
| WF006 | ضغط التأكيد مرتين يخصم مرة واحدة | PASS | 47.28 |
| WF007 | انقطاع الرد واسترجاع نفس نتيجة التحويل | PASS | 50.5 |
| WF008 | الرصيد ما يكفي ويا الأجور | PASS | 46.69 |
| WF009 | حساب حسن ما يؤكد مراجعة أمينة | PASS | 54.44 |
| WF010 | انتهاء صلاحية المراجعة يمنع الخصم | PASS | 38.18 |

The JSON companion includes each declared final-state oracle, actual event facts, assertions and transaction IDs. Session and confirmation credentials are excluded.
