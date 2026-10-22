"""Read-only payment context and local review-decision evidence.

No model decides risk thresholds, invents ledger figures, or sends support
messages. These small helpers support Topic 04; they are not complete submissions
for the fraud, merchant, or support-pipeline topics.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from typing import Any

from agent import normalize
from core import MockWallet, WalletError, money_text, utc_iso

RISK_RULES = [
    {"id": "NEW_RECIPIENT", "rule": "No successful transfer to this saved name in the latest 100 owner-scoped records; known fixture display prefixes are removed before comparison."},
    {"id": "LARGE_SHARE", "rule": "The proposed total debit is at least 50% of the current available balance."},
    {"id": "SCAM_SCRIPT", "rule": "The current request mentions a prize/processing fee, a safe account, or urgency with a transfer."},
]


def _history_name(record: dict[str, Any]) -> str:
    value = normalize(record["counterparty"])
    # Original read-only fixtures contain a display prefix instead of a plain
    # name. Remove that exact prefix only for those fixture records, so a known
    # recipient does not generate a misleading first-recipient warning.
    if record["id"].startswith("tx_history_"):
        value = value.removeprefix("تحويل تجريبي الي ")
    return value


class PaymentAssist:
    def __init__(self, wallet: MockWallet) -> None:
        self.wallet = wallet
        # A SQLite connection context commits/rolls back but does not close.
        # Close explicitly so advisory calls cannot retain Windows file handles.
        with closing(sqlite3.connect(wallet.database_path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS review_context (
                    draft_id TEXT NOT NULL, version INTEGER NOT NULL,
                    owner_user_id TEXT NOT NULL, context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (draft_id, version)
                );
                CREATE TABLE IF NOT EXISTS review_decisions (
                    draft_id TEXT NOT NULL, version INTEGER NOT NULL,
                    owner_user_id TEXT NOT NULL, decision TEXT NOT NULL,
                    risk_codes_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY (draft_id, version, decision)
                );
            """)

    def attach_context(self, owner: str, draft: dict[str, Any], message: str = "") -> dict[str, Any]:
        """Store advisory evidence separately from the immutable debit payload."""
        with closing(sqlite3.connect(self.wallet.database_path)) as connection, connection:
            existing = connection.execute(
                "SELECT context_json FROM review_context WHERE draft_id=? AND version=? AND owner_user_id=?",
                (draft["id"], draft["version"], owner),
            ).fetchone()
        if existing and not message:
            return {**draft, "payment_context": json.loads(existing[0])}
        review = draft["review"]
        balance = self.wallet.get_balance(owner)["available_minor"]
        total = review["total_debit_minor"]
        history = self.wallet.get_history(owner, 100)["items"]
        signals: list[dict[str, str]] = []
        if draft["kind"] == "transfer" and not any(
            item["status"] == "SUCCEEDED" and item["kind"] == "transfer"
            and _history_name(item) == normalize(review["recipient_or_biller"]) for item in history
        ):
            signals.append({"code": "NEW_RECIPIENT", "title": "ما عدنا تحويل ناجح سابق لهذا الاسم بالسجل المعروض", "explanation": "تأكد من هوية المستلم بطريقة تعرفها. هذا تنبيه من آخر ١٠٠ سجل، مو دليل على احتيال."})
        if balance > 0 and total * 2 >= balance:
            signals.append({"code": "LARGE_SHARE", "title": "هالعملية تستخدم نص رصيدك أو أكثر", "explanation": "راجع المبلغ والرسوم والرصيد اللي يبقى. القاعدة الحسابية: إجمالي الخصم ≥ ٥٠٪ من الرصيد الحالي."})
        normalized = normalize(message)
        if any(term in normalized for term in ("جائزه", "جائزة", "ربحت", "رسوم استلام", "رسوم معالجة", "حساب امن", "safe account", "prize", "processing fee")) or (
            any(term in normalized for term in ("بسرعه", "بسرعة", "فورا", "مستعجل", "urgent"))
            and any(term in normalized for term in ("حول", "تحويل", "دز", "send", "transfer"))
        ):
            signals.append({"code": "SCAM_SCRIPT", "title": "الطلب يشبه نمط استعجال أو جائزة أو حساب آمن", "explanation": "وقف لحظة واتصل بالشخص من رقم تعرفه. طلب فلوس حتى تستلم جائزة أو تنقلها لحساب «آمن» يستحق التحقق. القرار يبقى إلك قبل التأكيد."})
        # Preserve a prior message-derived warning if a menu/status read refreshes
        # the same review; do not store raw chat text in the audit tables.
        if existing:
            old = json.loads(existing[0])
            codes = {item["code"] for item in signals}
            signals.extend(item for item in old.get("signals", []) if item["code"] not in codes)
        context = {
            "advisory": True, "signals": signals,
            "available_before_minor": balance,
            "estimated_after_minor": balance - total,
            "currency": "IQD", "checked_at": utc_iso(),
            "balance_note": "تقدير وقت المراجعة: الرصيد الحالي ناقص المبلغ والرسوم. الخادم يعيد فحص الرصيد عند التأكيد.",
            "scope": "Rules on synthetic records only; not a fraud verdict or a guarantee of safety.",
        }
        with closing(sqlite3.connect(self.wallet.database_path)) as connection, connection:
            connection.execute(
                "INSERT OR REPLACE INTO review_context VALUES (?, ?, ?, ?, ?)",
                (draft["id"], draft["version"], owner, json.dumps(context, ensure_ascii=False), utc_iso()),
            )
        return {**draft, "payment_context": context}

    def record_decision(self, owner: str, draft: dict[str, Any], decision: str) -> None:
        if decision not in {"CONFIRMED", "CANCELLED"}:
            raise ValueError("Unsupported review decision")
        # Core cancellation invalidates credentials by incrementing the version.
        # The user's choice concerned the preceding displayed review.
        review_version = draft["version"] - (1 if decision == "CANCELLED" else 0)
        with closing(sqlite3.connect(self.wallet.database_path)) as connection, connection:
            row = connection.execute(
                "SELECT context_json FROM review_context WHERE draft_id=? AND version=? AND owner_user_id=?",
                (draft["id"], review_version, owner),
            ).fetchone()
            codes = [item["code"] for item in json.loads(row[0]).get("signals", [])] if row else []
            connection.execute(
                "INSERT OR IGNORE INTO review_decisions VALUES (?, ?, ?, ?, ?, ?)",
                (draft["id"], review_version, owner, decision, json.dumps(codes), utc_iso()),
            )

    def wallet_insights(self, owner: str) -> dict[str, Any]:
        history = self.wallet.get_history(owner, 100)["items"]
        succeeded = [item for item in history if item["status"] == "SUCCEEDED"]
        unknown = [item for item in history if item["status"] == "UNKNOWN"]
        failed = [item for item in history if item["status"] == "FAILED"]
        balance = self.wallet.get_balance(owner)
        total = sum(item["amount_minor"] for item in succeeded)
        return {
            "kind": "wallet_insights", "title": "أرقام واضحة من محفظتك التجريبية",
            "message": "الأرقام محسوبة من السجل، مو تخمين من النموذج. البيانات التاريخية أمثلة مستقلة ولا تعيد بناء رصيد البداية.",
            "items": [
                {"label": "الرصيد الحالي", "value": balance["formatted"]},
                {"label": "إجمالي الخصم الناجح في السجلات المعروضة", "value": money_text(total)},
                {"label": "عمليات ناجحة معروضة", "value": len(succeeded)},
                {"label": "حالات غير مؤكدة تحتاج متابعة", "value": len(unknown)},
                {"label": "عمليات فاشلة معروضة", "value": len(failed)},
            ],
            "available_minor": balance["available_minor"], "successful_total_minor": total,
            "unknown_count": len(unknown), "failed_count": len(failed),
            "source_records": [{"id": item["id"], "reference": item["reference"], "amount_minor": item["amount_minor"], "status": item["status"], "counterparty": item["counterparty"]} for item in history],
            "scope": "Latest 100 owner-scoped synthetic records. Not income, profit, or a cash-flow forecast.",
            "next_step": "إذا حالة عملية مو واضحة، افحص نفس المرجع قبل ما تعيد الدفع.",
        }

    def support_draft(self, owner: str, transaction_id: str, issue: str) -> dict[str, Any]:
        if not transaction_id.strip() or len(transaction_id) > 100 or not issue.strip() or len(issue) > 500:
            raise WalletError("INVALID_SUPPORT_DETAILS", "اكتب مرجع العملية ووصفاً قصيراً للمشكلة، بحد أقصى ٥٠٠ حرف.")
        if re.search(r"\b(?:pin|otp|bearer|api[_ -]?key|session[_ -]?(?:id|token))\b|رقم سري|رمز الدخول", issue, re.IGNORECASE):
            raise WalletError("SECRET_IN_SUPPORT", "لا تضع رمز دخول أو PIN/OTP أو مفتاح API في طلب الدعم.")
        transaction = self.wallet.get_transaction_status(owner, transaction_id.strip())
        status = transaction["status"]
        next_step = {
            "UNKNOWN": "افحص نفس المرجع مرة ثانية. لا تعيد الدفع قبل معرفة النتيجة؛ المسودة التالية تحتاج مراجعتك قبل مشاركتها مع الدعم.",
            "FAILED": "السجل يذكر فشل العملية. تحقق من السبب قبل محاولة جديدة؛ لا نفترض أن المشكلة انحلت.",
            "SUCCEEDED": "السجل يذكر نجاح العملية. راجع المستلم والمرجع؛ إذا عندك اعتراض اشرح المشكلة للدعم بدون إعادة التحويل.",
        }[status]
        facts = [
            ("مرجع العملية", transaction["reference"]),
            ("الحالة المسجلة", status),
            ("المستلم", transaction["counterparty"]),
            ("الخصم المسجل", money_text(transaction["debit_minor"])),
            ("التاريخ", transaction["created_at"]),
        ]
        draft_text = "مسودة دعم — بيانات تجريبية فقط\n" + "\n".join(f"{label}: {value}" for label, value in facts) + "\nوصف المستخدم (غير متحقق): " + issue.strip() + "\nالخطوة المقترحة: " + next_step
        return {
            "kind": "support_draft", "title": "مسودة طلب دعم للمراجعة",
            "message": "المسودة باقية عندك. ما انرسلت لأي جهة وما انفتح طلب دعم خارجي.",
            "items": [{"label": label, "value": value} for label, value in facts],
            "transaction_id": transaction["id"], "reference": transaction["reference"],
            "recorded_status": status, "user_issue": issue.strip(), "draft_text": draft_text,
            "next_step": next_step, "sent": False,
            "source": "Owner-scoped mock transaction record; issue is unverified user text.",
        }
