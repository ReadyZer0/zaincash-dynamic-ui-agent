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
_TRANSFER_RE = re.compile(r"(?:حول|حوّل|تحويل|دز|ارسل|أرسل|\btransfer\b|\bsend\b)", re.IGNORECASE)
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
        .replace("٬", ",")
    )
    value = re.sub(r"[\u064b-\u065f]", "", value)
    return " ".join(value.split())


def message_guard(message: str, conversation: dict[str, Any] | None = None) -> ChatDecision | None:
    """Conservative shared guard before either interpreter sees a request.

    These are transparent checks, not a complete natural-language safety proof.
    Ambiguous financial instructions are clarified before a draft is proposed.
    """
    state = conversation or {}
    normalized = normalize(message)
    if _SECRET_RE.search(message) or re.search(
        r"\b(?:bearer|api[_ -]?key|session[_ -]?(?:id|token))\b|رمز الدخول|توكن|مفتاح.*api",
        normalized,
        re.IGNORECASE,
    ):
        return ChatDecision("message", "لا ترسل رمز الدخول أو مفتاح API أو PIN/OTP بالمحادثة. الحساب يتحدد من جلسة التطبيق فقط.", conversation=state)
    if normalized in {"نعم", "اي", "ايوه", "كمل", "اكمل", "yes", "confirm"}:
        return ChatDecision("message", "الرسالة وحدها لا تنفذ أي دفع. راجع البطاقة واضغط زر التأكيد النهائي إذا أردت المتابعة.", conversation=state)
    if re.search(r"(?:(?:لا|ما)\s*(?:تحول|تدز|ترسل|تدفع)|لاتحول|(?:لا|ما|مو)\s+(?:اريد|تريد)\s+(?:احول|تحويل|ادز|ارسل|ادفع|دفع)|لا\s+تقوم\s+ب|الغ\s*(?:التحويل|الدفع)|\b(?:do not|don't|dont|cancel|stop)\b)", normalized):
        return ChatDecision("message", "ما راح أجهز دفعة من هالطلب. إذا عندك مراجعة مفتوحة استخدم زر إلغاء المراجعة لإبطالها.", conversation=state)
    if re.search(r"بدون\s*تاكيد|تجاوز\s*(?:التاكيد|المراجعه)|تجاهل\s*(?:التعليمات|القواعد)|من\s*حساب(?:ه|ها|هم|\s+شخص)|استخدم\s*جلسه|demo_(?:amina|hassan|operator)|\b(?:bypass|ignore instructions|without confirmation)\b", normalized):
        return ChatDecision("message", "ما أبدل الحساب من نص المحادثة ولا أتجاوز التأكيد. أقدر أجهز طلب واضح من حساب الجلسة الحالية فقط.", conversation=state)
    operation_words = re.findall(r"(?:حول|تحويل|دز(?!لي)|ارسل|ادفع|سدد|\btransfer\b|\bsend\b|\bpay\b)", normalized)
    if len(operation_words) > 1 and re.search(r"(?:\sو|\sثم|\sوبعد|\band\b|;|؛|\+)", normalized):
        question = "طلبك بيه أكثر من عملية. خل نكمل عملية وحدة كل مرة؛ شنو تريد نبدأ بيه؟"
        return ChatDecision("clarification", question, clarification={"field": "request", "prompt": question, "choices": []}, conversation={})
    if re.search(r"[-−–]\s*\d|(?:سالب|ناقص)\s+|\d[.٫]\d", normalized):
        question = "المبلغ يحتاج توضيح. اكتب مبلغاً موجباً وصحيحاً بالدينار، بدون إشارة سالب أو كسر."
        return ChatDecision("clarification", question, clarification={"field": "amount_minor", "prompt": question, "choices": []}, conversation={})
    groups = re.findall(r"\d+(?:,\d+)+", normalized)
    explicit_amounts = re.findall(r"\d+(?:,\d+)*\s*(?:الف|الاف|مليون|ملايين|دينار|iqd|k)(?:\b|\s|$)", normalized)
    if any(not re.fullmatch(r"\d{1,3}(?:,\d{3})+", group) for group in groups) or len(explicit_amounts) > 1:
        question = "كتبت أكثر من مبلغ أو فواصل مو واضحة. اكتب مبلغ واحد مثل ٥٠٬٠٠٠ دينار حتى ما نخمن."
        return ChatDecision("clarification", question, clarification={"field": "amount_minor", "prompt": question, "choices": []}, conversation={})
    if re.search(r"\b(?:usd|eur|dollars?|euros?)\b|دولار|يورو", normalized):
        question = "هذا النموذج يدعم الدينار العراقي فقط. شكد المبلغ بـ IQD؟ ما أحوّل العملة من عندي."
        return ChatDecision("clarification", question, clarification={"field": "amount_minor", "prompt": question, "choices": []}, conversation={})
    return None


def parse_iqd_amount(text: str) -> tuple[int | None, bool]:
    """Return ``(amount, ambiguous)`` without guessing a bare small number."""

    normalized = normalize(text)
    match = re.search(
        r"(?<![\d.])(\d{1,12}(?:[ ,]\d{3})*)(?:\s*(الف|الاف|مليون|ملايين|k|m))?(?:\s*(دينار|iqd))?(?![\d.])",
        normalized,
    )
    if not match:
        # Small explicit dialect vocabulary; unknown written numbers still ask
        # a question. A model is not silently emulated by this offline parser.
        words = {
            "خمسه وعشرين": 25, "خمسة وعشرين": 25,
            "عشره": 10, "عشرة": 10, "عشرين": 20, "ثلاثين": 30,
            "اربعين": 40, "خمسين": 50, "ستين": 60, "سبعين": 70,
            "ثمانين": 80, "تسعين": 90, "ميه": 100, "مية": 100,
            "مئه": 100, "مئة": 100,
        }
        for phrase, number in words.items():
            written = re.search(r"(?:^|\s)" + re.escape(phrase) + r"\s*(الف|الاف|مليون|ملايين)(?:\s|$|[،,.!?؟])", normalized)
            if written:
                return number * (1_000_000 if written.group(1) in {"مليون", "ملايين"} else 1_000), False
        return None, False
    digits = match.group(1).replace(" ", "").replace(",", "")
    value = int(digits)
    multiplier = match.group(2)
    has_currency = match.group(3)
    if multiplier:
        return value * (1_000_000 if multiplier in {"مليون", "ملايين", "m"} else 1_000), False
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
    return [contact for contact in contacts if any(
        re.search(r"(?:^|\s|ل)" + re.escape(normalize(str(contact[key])).split()[0]) + r"(?:\s|$|[،,.!?؟])", normalized)
        for key in ("display_name_ar", "display_name_en")
    )]


def _recipient_clarification(
    contacts: list[dict[str, Any]], conversation: dict[str, Any]
) -> ChatDecision:
    return ChatDecision(
        kind="clarification",
        text="تقصد أي مستلم؟ اختار الاسم المحفوظ حتى ما نخطئ بالتحويل.",
        clarification={
            "field": "recipient",
            "prompt": "تقصد أي مستلم؟",
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
    guarded = message_guard(message, state)
    if guarded is not None:
        return guarded
    normalized = normalize(message)
    if normalized in {"نعم", "اي", "ايوه", "كمل", "اكمل", "yes", "confirm"}:
        return ChatDecision(
            kind="message",
            text="الرسالة وحدها لا تنفذ أي دفع. راجع البطاقة واضغط زر التأكيد النهائي إذا أردت المتابعة.",
            conversation=state,
        )

    # Read-only routes take precedence over colloquial verbs such as "دزلي".
    # They return data immediately and never create a draft.
    if any(term in normalized for term in ("ملخص", "مصاريف", "صرفت", "insights", "summary")):
        return ChatDecision("view", "هذا ملخص محسوب من سجلات المحفظة التجريبية، ويا مراجع الأرقام.", "VIEW_WALLET_INSIGHTS", conversation=state)
    if any(term in normalized for term in ("دعم", "مساعده بعمليه", "support")):
        return ChatDecision("open_support_form", "أكدر أجهز مسودة طلب دعم من سجل العملية. تبقى عندك للمراجعة وما تنرسل لأي جهة.", "PREPARE_SUPPORT_REQUEST", conversation=state)
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

    if any(term in normalized for term in ("فاتور", "كهرباء", "bill")):
        if not bills:
            return ChatDecision(
                kind="message",
                text="ما لقيت فاتورة تجريبية محفوظة لهذا الحساب.",
                conversation=state,
            )
        categories = {
            "electricity": ("كهرب", "electric"),
            "mobile": ("موبايل", "هاتف", "mobile", "phone"),
            "internet": ("انترنت", "انترنيت", "internet"),
            "water": ("ماء", "water"),
        }
        requested = {key for key, terms in categories.items() if any(term in normalized for term in terms)}
        matches = [bill for bill in bills if normalize(str(bill["biller_name"])) in normalized or any(
            any(term in normalize(str(bill["biller_name"]) + " " + str(bill["provider"])) for term in categories[key])
            for key in requested
        )]
        generic = bool(re.fullmatch(r"(?:ادفع\s+)?(?:ال)?فاتور(?:ة|ه)(?:\s+(?:المحفوظة|المحفوظه)(?:\s+عندي)?|\s+عندي)?", normalized))
        if not requested and not matches and len(bills) == 1 and generic:
            matches = bills
        if len(matches) != 1 or len(requested) > 1:
            question = "أي فاتورة تقصد؟ هاي الفواتير المحفوظة بهذا الحساب فقط؛ ما أختار جهة بدالك."
            return ChatDecision("clarification", question, clarification={"field": "bill", "prompt": question, "choices": [{"id": bill["id"], "label": bill["biller_name"]} for bill in bills]}, conversation={})
        return ChatDecision(
            kind="prepare_bill",
            text="جهزت مراجعة فاتورة من البيانات التجريبية. راجعها ثم استخدم زر التأكيد النهائي.",
            bill_id=str(matches[0]["id"]),
            conversation={},
        )

    pending_decision = _try_pending_transfer(message, state, contacts)
    if pending_decision is not None:
        return pending_decision

    return ChatDecision(
        kind="message",
        text="أكدر أظهر الرصيد أو سجل الحركات أو رمز الاستلام، أو أجهز تحويل/فاتورة تجريبية للمراجعة.",
        conversation=state,
    )


def offline_model_contract() -> dict[str, tuple[str, ...]]:
    """Inspectable proof that an offline router has no commit-capable tool."""

    return {"allowed_action_ids": customer_tool_projection()}
