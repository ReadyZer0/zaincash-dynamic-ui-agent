"""Deterministic Iraqi-Arabic routing for the offline demonstration.

It deliberately returns a small declarative decision, never a URL, database
query, confirmation capability, or payment-commit instruction.  ``server.py``
validates every decision again and owns all effects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from action_registry import customer_tool_projection

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_SECRET_RE = re.compile(r"\b(?:pin|otp)\b|(?:رقم|رمز)\s*(?:سري|pin|otp)", re.IGNORECASE)
_TRANSFER_RE = re.compile(r"(?:حول|حوّل|تحويل|دز|ارسل|أرسل)")
_EDIT_RE = re.compile(r"(?:غير|غيّر|خلي|خلّي).{0,30}(?:مبلغ|الف|ألف|\d)")
_SCHEDULE_RE = re.compile(r"(?:جدول|جدولة|موعد|شهري|تكرار|recurr|schedule)")


@dataclass(frozen=True)
class ChatDecision:
    kind: str
    text: str
    action_id: str | None = None
    clarification: dict[str, Any] | None = None
    recipient_id: str | None = None
    amount_minor: int | None = None
    bill_id: str | None = None
    conversation: dict[str, Any] | None = None


def normalize(text: str) -> str:
    value = text.translate(_DIGITS).lower()
    value = (
        value.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ـ", "")
    )
    return " ".join(value.split())


def parse_iqd_amount(text: str) -> tuple[int | None, bool]:
    """Return ``(amount, ambiguous)`` without guessing a bare small number."""

    normalized = normalize(text)
    match = re.search(
        r"(?<!\d)(\d{1,7}(?:[ ,]\d{3})*)(?:\s*(الف|الاف|k))?(?:\s*(دينار|iqd))?(?!\d)",
        normalized,
    )
    if not match:
        return None, False
    digits = match.group(1).replace(" ", "").replace(",", "")
    value = int(digits)
    multiplier = match.group(2)
    has_currency = match.group(3)
    if multiplier:
        return value * 1_000, False
    # "حول 50" is intentionally not interpreted as fifty thousand; users must
    # say 50 ألف, 50,000, or include an explicit currency.
    if value < 1_000 and not has_currency:
        return None, True
    return value, False


def matching_contacts(
    message: str, contacts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    normalized = normalize(message)
    full_matches = [
        contact
        for contact in contacts
        if normalize(str(contact["display_name_ar"])) in normalized
        or normalize(str(contact["display_name_en"])) in normalized
    ]
    if full_matches:
        return full_matches
    if "علي" in normalized or re.search(r"\bali\b", normalized):
        return [
            contact
            for contact in contacts
            if "علي" in normalize(str(contact["display_name_ar"]))
            or normalize(str(contact["display_name_en"])).startswith("ali")
        ]
    return []


def _recipient_clarification(
    contacts: list[dict[str, Any]], conversation: dict[str, Any]
) -> ChatDecision:
    return ChatDecision(
        kind="clarification",
        text="تقصد أي علي؟ اختار الاسم المحفوظ حتى ما نخطئ بالتحويل.",
        clarification={
            "field": "recipient",
            "prompt": "تقصد أي علي؟",
            "choices": [
                {"id": str(contact["id"]), "label": str(contact["display_name_ar"])}
                for contact in contacts
            ],
        },
        conversation=conversation,
    )


def _amount_clarification(
    conversation: dict[str, Any], *, ambiguous: bool = False
) -> ChatDecision:
    text = (
        "المبلغ مو واضح. اكتب مثلاً ٥٠ ألف دينار أو ٥٠,٠٠٠ IQD."
        if ambiguous
        else "شكد المبلغ بالدينار العراقي؟ اكتب مثلاً ٥٠ ألف دينار."
    )
    return ChatDecision(
        kind="clarification",
        text=text,
        clarification={"field": "amount_minor", "prompt": text, "choices": []},
        conversation=conversation,
    )


def _recipient_needed(conversation: dict[str, Any]) -> ChatDecision:
    text = "لمن تريد التحويل؟ اكتب اسم المستلم المحفوظ أو اختاره من جهات الاتصال."
    return ChatDecision(
        kind="clarification",
        text=text,
        clarification={"field": "recipient", "prompt": text, "choices": []},
        conversation=conversation,
    )


def _provider_needed(conversation: dict[str, Any]) -> ChatDecision:
    text = "أي محفظة يستخدم المستلم؟ رقم الهاتف وحده ما يحدد مزود المحفظة."
    return ChatDecision(
        kind="clarification",
        text=text,
        clarification={"field": "provider", "prompt": text, "choices": []},
        conversation=conversation,
    )


def _try_pending_transfer(
    message: str, conversation: dict[str, Any], contacts: list[dict[str, Any]]
) -> ChatDecision | None:
    pending = conversation.get("pending")
    if not isinstance(pending, dict) or pending.get("intent") != "transfer":
        return None
    updated = {"pending": dict(pending)}
    amount, ambiguous = parse_iqd_amount(message)
    if amount is not None:
        updated["pending"]["amount_minor"] = amount
    matches = matching_contacts(message, contacts)
    if len(matches) == 1:
        updated["pending"]["recipient_id"] = matches[0]["id"]
    elif len(matches) > 1:
        return _recipient_clarification(matches, updated)
    if re.search(r"07\d{8,10}", normalize(message)) and not matches:
        updated["pending"]["needs_provider"] = True
        return _provider_needed(updated)
    if updated["pending"].get("needs_provider"):
        # This M1 slice has no unverified phone-recipient adapter. A provider
        # answer is clarified safely instead of inventing an identity.
        return _recipient_needed({"pending": {"intent": "transfer"}})
    if updated["pending"].get("recipient_id") and updated["pending"].get(
        "amount_minor"
    ):
        return ChatDecision(
            kind="prepare_transfer",
            text="جهزت مراجعة التحويل. راجع التفاصيل ثم استخدم زر التأكيد النهائي.",
            recipient_id=str(updated["pending"]["recipient_id"]),
            amount_minor=int(updated["pending"]["amount_minor"]),
            conversation={},
        )
    if not updated["pending"].get("recipient_id"):
        return _recipient_needed(updated)
    return _amount_clarification(updated, ambiguous=ambiguous)


def route_chat(
    message: str,
    conversation: dict[str, Any] | None,
    contacts: list[dict[str, Any]],
    bills: list[dict[str, Any]],
) -> ChatDecision:
    """Route a bounded, untrusted user message in offline mode."""

    state = conversation if isinstance(conversation, dict) else {}
    if _SECRET_RE.search(message):
        return ChatDecision(
            kind="message",
            text="لا ترسل رقمك السري أو رمز OTP هنا. استخدم الإدخال الآمن في التطبيق الحقيقي.",
            conversation=state,
        )
    normalized = normalize(message)
    if normalized in {"نعم", "اي", "ايوه", "كمل", "اكمل", "yes", "confirm"}:
        return ChatDecision(
            kind="message",
            text="الرسالة وحدها لا تنفذ أي دفع. راجع البطاقة واضغط زر التأكيد النهائي إذا أردت المتابعة.",
            conversation=state,
        )

    # Read-only routes take precedence over colloquial verbs such as "دزلي".
    # They return data immediately and never create a draft.
    if "qr" in normalized or "رمز الاستلام" in normalized or "رمز qr" in normalized:
        return ChatDecision(
            "view",
            "تفضل، هذا رمز الاستلام التجريبي.",
            "SHOW_RECEIVE_QR",
            conversation=state,
        )
    if "رصيد" in normalized or "balance" in normalized:
        return ChatDecision(
            "view",
            "هذا رصيدك في المحفظة التجريبية.",
            "VIEW_BALANCE",
            conversation=state,
        )
    if any(term in normalized for term in ("سجل", "حركات", "history", "معاملات")):
        return ChatDecision(
            "view",
            "هذه حركات المحفظة التجريبية المتاحة للقراءة.",
            "VIEW_HISTORY",
            conversation=state,
        )
    # An edit applies only to a draft that the server previously associated with
    # this session. It produces a new review/version, never an execution.
    active_draft_id = state.get("active_draft_id")
    if active_draft_id and _EDIT_RE.search(normalized):
        amount, ambiguous = parse_iqd_amount(message)
        if amount is None:
            return _amount_clarification(state, ambiguous=ambiguous)
        return ChatDecision(
            kind="edit_draft_amount",
            text="تم تحديث المسودة وإنشاء مراجعة جديدة؛ التأكيد السابق لم يعد صالحاً.",
            amount_minor=amount,
            conversation=state,
        )

    if _SCHEDULE_RE.search(normalized):
        return ChatDecision(
            kind="open_schedule_form",
            text=(
                "أكدر أجهز جدول تذكير شهري تجريبي. اختار المستلم والمبلغ "
                "ووقتاً مستقبلياً واضحاً؛ كل دفعة لاحقة تحتاج مراجعة وتأكيد جديدين."
            ),
            action_id="OPEN_SCHEDULED_TRANSFER",
            conversation=state,
        )

    if _TRANSFER_RE.search(normalized):
        amount, ambiguous = parse_iqd_amount(message)
        matches = matching_contacts(message, contacts)
        pending: dict[str, Any] = {"intent": "transfer"}
        if amount is not None:
            pending["amount_minor"] = amount
        if len(matches) == 1:
            pending["recipient_id"] = matches[0]["id"]
        if len(matches) > 1:
            return _recipient_clarification(matches, {"pending": pending})
        if re.search(r"07\d{8,10}", normalized) and not matches:
            return _provider_needed({"pending": pending})
        if pending.get("recipient_id") and pending.get("amount_minor"):
            return ChatDecision(
                kind="prepare_transfer",
                text="جهزت مراجعة التحويل. راجع التفاصيل ثم استخدم زر التأكيد النهائي.",
                recipient_id=str(pending["recipient_id"]),
                amount_minor=int(pending["amount_minor"]),
                conversation={},
            )
        if not pending.get("recipient_id"):
            return _recipient_needed({"pending": pending})
        return _amount_clarification({"pending": pending}, ambiguous=ambiguous)

    pending_decision = _try_pending_transfer(message, state, contacts)
    if pending_decision is not None:
        return pending_decision

    if any(term in normalized for term in ("فاتور", "كهرباء", "bill")):
        if not bills:
            return ChatDecision(
                kind="message",
                text="ما لقيت فاتورة تجريبية محفوظة لهذا الحساب.",
                conversation=state,
            )
        return ChatDecision(
            kind="prepare_bill",
            text="جهزت مراجعة فاتورة من البيانات التجريبية. راجعها ثم استخدم زر التأكيد النهائي.",
            bill_id=str(bills[0]["id"]),
            conversation={},
        )

    return ChatDecision(
        kind="message",
        text="أكدر أظهر الرصيد أو سجل الحركات أو رمز الاستلام، أو أجهز تحويل/فاتورة تجريبية للمراجعة.",
        conversation=state,
    )


def offline_model_contract() -> dict[str, tuple[str, ...]]:
    """Inspectable proof that an offline router has no commit-capable tool."""

    return {"allowed_action_ids": customer_tool_projection()}
