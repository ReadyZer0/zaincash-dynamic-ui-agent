"""Server-owned action definitions for the offline mock-wallet demo.

Chat can only name these action IDs. It never supplies a route, handler, or
authorization rule of its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ActionDefinition:
    action_id: str
    label_ar: str
    label_en: str
    kind: str
    component: str
    handler_name: str
    requires_confirmation: bool
    roles: tuple[str, ...]
    parameters: Mapping[str, type]

    def public(self) -> dict[str, object]:
        return {
            "id": self.action_id,
            "label_ar": self.label_ar,
            "label_en": self.label_en,
            "kind": self.kind,
            "component": self.component,
            "handler_name": self.handler_name,
            "requires_confirmation": self.requires_confirmation,
            "enabled": True,
            "parameters": list(self.parameters),
        }


ACTION_REGISTRY: dict[str, ActionDefinition] = {
    "SHOW_RECEIVE_QR": ActionDefinition(
        "SHOW_RECEIVE_QR",
        "إظهار رمز الاستلام",
        "Show receive QR",
        "view",
        "receive-qr",
        "get_receive_qr",
        False,
        ("customer",),
        {},
    ),
    "VIEW_BALANCE": ActionDefinition(
        "VIEW_BALANCE",
        "عرض الرصيد",
        "View balance",
        "view",
        "balance",
        "get_balance",
        False,
        ("customer",),
        {},
    ),
    "VIEW_HISTORY": ActionDefinition(
        "VIEW_HISTORY",
        "سجل الحركات",
        "Transaction history",
        "view",
        "history",
        "get_history",
        False,
        ("customer",),
        {},
    ),
    "OPEN_TRANSFER": ActionDefinition(
        "OPEN_TRANSFER",
        "تحويل أموال",
        "Transfer money",
        "prepare",
        "transfer-review",
        "prepare_transfer",
        True,
        ("customer",),
        {"recipient_id": str, "amount_minor": int, "currency": str},
    ),
    "OPEN_SCHEDULED_TRANSFER": ActionDefinition(
        "OPEN_SCHEDULED_TRANSFER",
        "جدولة تحويل",
        "Schedule a transfer",
        "prepare",
        "scheduled-transfer-review",
        "prepare_scheduled_transfer",
        True,
        ("customer",),
        {
            "recipient_id": str,
            "amount_minor": int,
            "currency": str,
            "scheduled_for": str,
            "timezone": str,
            "recurrence": str,
        },
    ),
    "OPEN_BILL_PAYMENT": ActionDefinition(
        "OPEN_BILL_PAYMENT",
        "دفع فاتورة",
        "Pay a bill",
        "prepare",
        "bill-review",
        "prepare_bill_payment",
        True,
        ("customer",),
        {"bill_id": str},
    ),
    "CHECK_PAYMENT_STATUS": ActionDefinition(
        "CHECK_PAYMENT_STATUS",
        "التحقق من حالة الدفع",
        "Check payment status",
        "view",
        "payment-status",
        "get_transaction_status",
        False,
        ("customer",),
        {"transaction_id": str},
    ),
    "VIEW_WALLET_INSIGHTS": ActionDefinition(
        "VIEW_WALLET_INSIGHTS", "ملخص المحفظة بالأدلة", "Wallet insights", "view",
        "wallet-insights", "wallet_insights", False, ("customer",), {},
    ),
    "PREPARE_SUPPORT_REQUEST": ActionDefinition(
        "PREPARE_SUPPORT_REQUEST", "جهز طلب دعم", "Prepare support draft", "view",
        "support-draft", "support_draft", False, ("customer",),
        {"transaction_id": str, "issue": str},
    ),
    "VIEW_OPERATOR_ISSUES": ActionDefinition(
        "VIEW_OPERATOR_ISSUES",
        "طلبات الدعم التجريبية",
        "Mock support desk",
        "view",
        "operator-issues",
        "operator_issues_view",
        False,
        ("operator",),
        {},
    ),
}


def get_action(action_id: str) -> ActionDefinition | None:
    return ACTION_REGISTRY.get(action_id)


def actions_for_role(role: str) -> list[dict[str, object]]:
    return [
        definition.public()
        for definition in ACTION_REGISTRY.values()
        if role in definition.roles
    ]


def customer_tool_projection() -> tuple[str, ...]:
    """The only action IDs an offline or future model may select.

    Confirmation, database, session, and raw-token operations are deliberately
    absent. The HTTP confirmation endpoint is browser-only and server checked.
    """

    return tuple(
        action_id
        for action_id, definition in ACTION_REGISTRY.items()
        if "customer" in definition.roles
    )
