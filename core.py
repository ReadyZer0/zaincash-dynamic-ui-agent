"""SQLite-backed, synthetic mock-wallet domain logic.

This module deliberately owns balances, action consequences, draft state and
confirmation validation.  It has no model client, payment gateway, or network
dependency.  Amounts are integer Iraqi dinar minor units (IQD has no fraction
in this demo).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from qr_code import encode as encode_qr

UTC = timezone.utc
MAX_TRANSFER_MINOR = 1_000_000
CONFIRMATION_LIFETIME = timedelta(minutes=5)
SESSION_LIFETIME = timedelta(hours=8)
SCHEDULE_MINIMUM_LEAD = timedelta(minutes=5)
SCHEDULE_TIMEZONE = "Asia/Baghdad"
SCHEDULE_ZONE = ZoneInfo(SCHEDULE_TIMEZONE)
SCHEDULE_RECURRENCE = "MONTHLY"
SCHEDULE_AUTHORIZATION_MODE = "REMIND_AND_PREPARE"


class WalletError(Exception):
    """A safe, public domain error suitable for the HTTP boundary."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class AuthenticationError(WalletError):
    def __init__(self, message: str = "A valid demo session is required.") -> None:
        super().__init__("AUTH_REQUIRED", message, 401)


class ForbiddenError(WalletError):
    def __init__(
        self, message: str = "This demo session is not allowed to use that action."
    ) -> None:
        super().__init__("FORBIDDEN", message, 403)


class NotFoundError(WalletError):
    def __init__(
        self,
        code: str = "NOT_FOUND",
        message: str = "The requested record was not found.",
    ) -> None:
        super().__init__(code, message, 404)


class ConflictError(WalletError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 409)


@dataclass(frozen=True)
class IssuedDraft:
    """A server-internal confirmation capability plus a browser-safe draft."""

    draft: dict[str, Any]
    confirmation_token: str


@dataclass(frozen=True)
class IssuedScheduleDraft:
    """A separate, no-debit capability for a mock schedule configuration."""

    schedule_draft: dict[str, Any]
    confirmation_token: str


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def utc_iso(value: datetime | None = None) -> str:
    return (
        (value or utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def money_text(amount_minor: int, currency: str = "IQD") -> str:
    return f"{amount_minor:,} {currency}"


class MockWallet:
    """A small transactional wallet with isolated fictional fixture users."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=5, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialise(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('customer', 'operator'))
                );
                CREATE TABLE IF NOT EXISTS accounts (
                    user_id TEXT PRIMARY KEY REFERENCES users(id),
                    available_minor INTEGER NOT NULL CHECK(available_minor >= 0),
                    currency TEXT NOT NULL CHECK(currency = 'IQD')
                );
                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL REFERENCES users(id),
                    display_name_ar TEXT NOT NULL,
                    display_name_en TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    account_identifier TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bills (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL REFERENCES users(id),
                    biller_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    account_identifier TEXT NOT NULL,
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    currency TEXT NOT NULL CHECK(currency = 'IQD')
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    role TEXT NOT NULL CHECK(role IN ('customer', 'operator')),
                    csrf_token TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    conversation_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL REFERENCES users(id),
                    issuing_session_id TEXT REFERENCES sessions(id),
                    kind TEXT NOT NULL CHECK(kind IN ('transfer', 'bill_payment')),
                    state TEXT NOT NULL CHECK(state IN (
                        'NEEDS_DETAILS', 'READY_FOR_REVIEW', 'AWAITING_CONFIRMATION',
                        'SUBMITTED', 'SUCCEEDED', 'FAILED', 'UNKNOWN', 'CANCELLED', 'EXPIRED'
                    )),
                    version INTEGER NOT NULL CHECK(version > 0),
                    payload_json TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    quote_expires_at TEXT NOT NULL,
                    confirmation_token_hash TEXT,
                    confirmation_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cancelled_at TEXT
                );
                CREATE TABLE IF NOT EXISTS draft_revisions (
                    draft_id TEXT NOT NULL REFERENCES drafts(id),
                    version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(draft_id, version)
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    draft_id TEXT UNIQUE REFERENCES drafts(id),
                    owner_user_id TEXT NOT NULL REFERENCES users(id),
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('SUCCEEDED', 'FAILED', 'UNKNOWN')),
                    debit_minor INTEGER NOT NULL CHECK(debit_minor >= 0),
                    currency TEXT NOT NULL CHECK(currency = 'IQD'),
                    counterparty TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    reference TEXT NOT NULL UNIQUE,
                    receipt_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_transactions_owner_created
                    ON transactions(owner_user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS provider_results (
                    transaction_id TEXT PRIMARY KEY REFERENCES transactions(id),
                    status TEXT NOT NULL CHECK(status IN ('SUCCEEDED', 'FAILED', 'UNKNOWN')) ,
                    receipt_json TEXT,
                    updated_at TEXT NOT NULL
                );
                -- Schedule configuration is deliberately separate from payment
                -- drafts and transactions: it has no executable debit path.
                CREATE TABLE IF NOT EXISTS schedule_drafts (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL REFERENCES users(id),
                    issuing_session_id TEXT NOT NULL REFERENCES sessions(id),
                    state TEXT NOT NULL CHECK(state IN (
                        'AWAITING_CONFIRMATION', 'SCHEDULED_MOCK_ONLY', 'CANCELLED', 'EXPIRED'
                    )),
                    version INTEGER NOT NULL CHECK(version > 0),
                    payload_json TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    confirmation_token_hash TEXT,
                    confirmation_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cancelled_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_schedule_drafts_owner_created
                    ON schedule_drafts(owner_user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS scheduled_payment_plans (
                    id TEXT PRIMARY KEY,
                    schedule_draft_id TEXT NOT NULL UNIQUE REFERENCES schedule_drafts(id),
                    owner_user_id TEXT NOT NULL REFERENCES users(id),
                    recipient_id TEXT NOT NULL REFERENCES contacts(id),
                    recipient_or_biller TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    account_identifier TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status = 'ACTIVE_MOCK_ONLY'),
                    scheduled_for TEXT NOT NULL,
                    timezone TEXT NOT NULL CHECK(timezone = 'Asia/Baghdad'),
                    recurrence TEXT NOT NULL CHECK(recurrence = 'MONTHLY'),
                    authorization_mode TEXT NOT NULL CHECK(authorization_mode = 'REMIND_AND_PREPARE'),
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    fee_minor INTEGER NOT NULL CHECK(fee_minor >= 0),
                    total_debit_minor INTEGER NOT NULL CHECK(total_debit_minor > 0),
                    currency TEXT NOT NULL CHECK(currency = 'IQD'),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_scheduled_payment_plans_owner_due
                    ON scheduled_payment_plans(owner_user_id, scheduled_for ASC);
                """
            )
            self._ensure_compatibility_columns(connection)
            self._seed(connection)
        finally:
            connection.close()

    @staticmethod
    def _ensure_compatibility_columns(connection: sqlite3.Connection) -> None:
        """Harden local databases created by earlier demo builds safely."""
        session_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(sessions)")
        }
        if "conversation_json" not in session_columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN conversation_json TEXT NOT NULL DEFAULT '{}'"
            )
        draft_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(drafts)")
        }
        if "issuing_session_id" not in draft_columns:
            # Existing drafts remain readable but cannot be confirmed until a
            # fresh, session-bound review is prepared.
            connection.execute("ALTER TABLE drafts ADD COLUMN issuing_session_id TEXT")

    @staticmethod
    def _seed(connection: sqlite3.Connection) -> None:
        connection.executemany(
            "INSERT OR IGNORE INTO users(id, display_name, role) VALUES (?, ?, ?)",
            (
                ("demo_amina", "أمينة التجريبية", "customer"),
                ("demo_hassan", "حسن التجريبي", "customer"),
                ("demo_operator", "مشغّل العرض التجريبي", "operator"),
            ),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO accounts(user_id, available_minor, currency) VALUES (?, ?, 'IQD')",
            (("demo_amina", 150_000), ("demo_hassan", 87_500)),
        )
        connection.executemany(
            """INSERT OR IGNORE INTO contacts
               (id, owner_user_id, display_name_ar, display_name_en, provider, account_identifier)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                (
                    "contact_ali_diaa",
                    "demo_amina",
                    "علي ضياء",
                    "Ali Diaa",
                    "ZainCash mock",
                    "0770•••483",
                ),
                (
                    "contact_ali_mohammed",
                    "demo_amina",
                    "علي محمد",
                    "Ali Mohammed",
                    "ZainCash mock",
                    "0771•••917",
                ),
                (
                    "contact_amina",
                    "demo_hassan",
                    "أمينة",
                    "Amina",
                    "ZainCash mock",
                    "0770•••001",
                ),
            ),
        )
        connection.executemany(
            """INSERT OR IGNORE INTO bills
               (id, owner_user_id, biller_name, provider, account_identifier, amount_minor, currency)
               VALUES (?, ?, ?, ?, ?, ?, 'IQD')""",
            (
                (
                    "bill_electricity_home",
                    "demo_amina",
                    "كهرباء المنزل التجريبية",
                    "Mock Electricity",
                    "BILL••2841",
                    45_000,
                ),
                (
                    "bill_mobile_hassan",
                    "demo_hassan",
                    "فاتورة موبايل تجريبية",
                    "Mock Mobile",
                    "POST••1640",
                    18_000,
                ),
            ),
        )
        connection.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES ('policy_version', 'mock-policy-v1')"
        )
        # Fixed synthetic history examples make both demo profiles useful during
        # a walkthrough. They never post to or change the available balances.
        history_fixtures = (
            (
                "tx_history_amina_001",
                "demo_amina",
                "transfer",
                12_500,
                "تحويل تجريبي إلى علي ضياء",
                "ZainCash mock",
                "MOCK-HIST-AMINA-001",
                "2026-09-21T09:00:00Z",
            ),
            (
                "tx_history_amina_002",
                "demo_amina",
                "transfer",
                25_000,
                "تحويل تجريبي إلى علي محمد",
                "ZainCash mock",
                "MOCK-HIST-AMINA-002",
                "2026-09-18T11:20:00Z",
            ),
            (
                "tx_history_amina_003",
                "demo_amina",
                "bill_payment",
                45_000,
                "كهرباء المنزل التجريبية",
                "Mock Electricity",
                "MOCK-HIST-AMINA-003",
                "2026-09-12T08:15:00Z",
            ),
            (
                "tx_history_hassan_001",
                "demo_hassan",
                "bill_payment",
                18_000,
                "فاتورة موبايل تجريبية",
                "Mock Mobile",
                "MOCK-HIST-HASSAN-001",
                "2026-09-20T13:00:00Z",
            ),
            (
                "tx_history_hassan_002",
                "demo_hassan",
                "transfer",
                9_500,
                "تحويل تجريبي إلى أمينة",
                "ZainCash mock",
                "MOCK-HIST-HASSAN-002",
                "2026-09-16T10:45:00Z",
            ),
            (
                "tx_history_hassan_003",
                "demo_hassan",
                "bill_payment",
                10_000,
                "فاتورة موبايل تجريبية",
                "Mock Mobile",
                "MOCK-HIST-HASSAN-003",
                "2026-09-08T07:30:00Z",
            ),
        )
        for (
            transaction_id,
            owner_user_id,
            kind,
            debit_minor,
            counterparty,
            provider,
            reference,
            created_at,
        ) in history_fixtures:
            receipt = json.dumps(
                {
                    "receipt_type": "synthetic_history_fixture",
                    "reference": reference,
                    "note": "Synthetic demo record; no external payment occurred.",
                },
                ensure_ascii=False,
            )
            connection.execute(
                """INSERT OR IGNORE INTO transactions
                   (id, draft_id, owner_user_id, kind, status, debit_minor, currency,
                    counterparty, provider, reference, receipt_json, created_at, updated_at)
                   VALUES (?, NULL, ?, ?, 'SUCCEEDED', ?, 'IQD', ?, ?, ?, ?, ?, ?)""",
                (
                    transaction_id,
                    owner_user_id,
                    kind,
                    debit_minor,
                    counterparty,
                    provider,
                    reference,
                    receipt,
                    created_at,
                    created_at,
                ),
            )
        # Bring forward the original fixed fixture without touching user-created
        # transactions or any account balance in existing local demo databases.
        connection.execute(
            """UPDATE transactions
               SET counterparty = ?, created_at = ?, updated_at = ?
               WHERE id = ? AND owner_user_id = ? AND draft_id IS NULL
                 AND reference = ? AND receipt_json LIKE '%synthetic_history_fixture%'""",
            (
                "تحويل تجريبي إلى علي ضياء",
                "2026-09-21T09:00:00Z",
                "2026-09-21T09:00:00Z",
                "tx_history_amina_001",
                "demo_amina",
                "MOCK-HIST-AMINA-001",
            ),
        )

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _row_or_not_found(
        row: sqlite3.Row | None, code: str = "NOT_FOUND"
    ) -> sqlite3.Row:
        if row is None:
            raise NotFoundError(code)
        return row

    def create_demo_session(self, user_id: str) -> dict[str, Any]:
        if not isinstance(user_id, str) or len(user_id) > 80:
            raise AuthenticationError("Choose one of the supplied demo identities.")
        with self._write_transaction() as connection:
            user = connection.execute(
                "SELECT id, display_name, role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if user is None:
                raise AuthenticationError("Choose one of the supplied demo identities.")
            session_id = secrets.token_urlsafe(24)
            csrf_token = secrets.token_urlsafe(24)
            expires_at = utc_iso(utc_now() + SESSION_LIFETIME)
            connection.execute(
                "INSERT INTO sessions(id, user_id, role, csrf_token, expires_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, user["id"], user["role"], csrf_token, expires_at),
            )
        return {
            "id": session_id,
            "user_id": user["id"],
            "role": user["role"],
            "csrf_token": csrf_token,
            "expires_at": expires_at,
        }

    def require_session(
        self,
        session_id: str | None,
        csrf_token: str | None = None,
        *,
        require_csrf: bool = False,
    ) -> dict[str, str]:
        if not session_id or len(session_id) > 200:
            raise AuthenticationError()
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT id, user_id, role, csrf_token, expires_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None or parse_utc(row["expires_at"]) <= utc_now():
            raise AuthenticationError(
                "This demo session has expired. Start a new demo session."
            )
        if require_csrf and (
            not csrf_token or not hmac.compare_digest(row["csrf_token"], csrf_token)
        ):
            raise ForbiddenError("The request did not include the session CSRF token.")
        return {"id": row["id"], "user_id": row["user_id"], "role": row["role"]}

    def get_user(self, user_id: str) -> dict[str, str]:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT id, display_name, role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        finally:
            connection.close()
        row = self._row_or_not_found(row, "USER_NOT_FOUND")
        return {
            "id": row["id"],
            "display_name": row["display_name"],
            "role": row["role"],
        }

    def get_conversation(self, session_id: str) -> dict[str, Any]:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT conversation_json FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise AuthenticationError()
        try:
            value = json.loads(row["conversation_json"])
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def set_conversation(self, session_id: str, conversation: dict[str, Any]) -> None:
        # Chat state is bounded and contains no raw transcript or confirmation
        # capability. A normal chat turn must not overwrite either independent
        # active review pointer created atomically by the domain layer.
        if not isinstance(conversation, dict):
            raise WalletError("INVALID_CONVERSATION", "Conversation state is invalid.")
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT conversation_json FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise AuthenticationError()
            merged = dict(conversation)
            current = self._conversation_from_session(row)
            for key in ("active_draft_id", "active_schedule_draft_id"):
                current_active = current.get(key)
                if current_active and merged.get(key) != current_active:
                    merged[key] = current_active
            serialized = json.dumps(
                merged, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            if len(serialized) > 4_000:
                raise WalletError(
                    "CONVERSATION_TOO_LARGE",
                    "The temporary conversation state is too large.",
                )
            connection.execute(
                "UPDATE sessions SET conversation_json = ? WHERE id = ?",
                (serialized, session_id),
            )

    def get_balance(self, owner_user_id: str) -> dict[str, Any]:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT available_minor, currency FROM accounts WHERE user_id = ?",
                (owner_user_id,),
            ).fetchone()
        finally:
            connection.close()
        row = self._row_or_not_found(row, "ACCOUNT_NOT_FOUND")
        return {
            "available_minor": row["available_minor"],
            "currency": row["currency"],
            "formatted": money_text(row["available_minor"], row["currency"]),
            "source": "synthetic mock-wallet ledger",
        }

    def get_receive_qr(self, owner_user_id: str) -> dict[str, Any]:
        # Validate the owner exists rather than allowing arbitrary QR generation.
        self.get_user(owner_user_id)
        owner_code = {
            "demo_amina": "AMINA",
            "demo_hassan": "HASSAN",
            "demo_operator": "OPS",
        }.get(owner_user_id, "TEST")
        payload = f"MOCK-RECEIVE|{owner_code}|NOT-PAYABLE"
        return {
            "kind": "receive_qr",
            "payload": payload,
            "matrix": encode_qr(payload),
            "format": "QR Model 2 v2-L",
            "payable": False,
            "label": "رمز استلام تجريبي فقط",
            "disclaimer": "هذا رمز خيالي للعرض فقط وليس رمز دفع أو تحويل حقيقي.",
        }

    def get_history(self, owner_user_id: str, limit: int = 30) -> dict[str, Any]:
        limit = max(1, min(int(limit), 100))
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT id, kind, status, debit_minor, currency, counterparty, provider, reference, created_at
                   FROM transactions WHERE owner_user_id = ? ORDER BY created_at DESC LIMIT ?""",
                (owner_user_id, limit),
            ).fetchall()
        finally:
            connection.close()
        items = [
            {
                "id": row["id"],
                "kind": row["kind"],
                "status": row["status"],
                "amount_minor": row["debit_minor"],
                "currency": row["currency"],
                "counterparty": row["counterparty"],
                "provider": row["provider"],
                "reference": row["reference"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        return {"kind": "history", "items": items, "scope": "mock wallet history only"}

    def contacts_for_owner(self, owner_user_id: str) -> list[dict[str, str]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT id, display_name_ar, display_name_en, provider, account_identifier
                   FROM contacts WHERE owner_user_id = ? ORDER BY display_name_ar""",
                (owner_user_id,),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def bills_for_owner(self, owner_user_id: str) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT id, biller_name, provider, account_identifier, amount_minor, currency
                   FROM bills WHERE owner_user_id = ? ORDER BY biller_name""",
                (owner_user_id,),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def get_schedule_transfer_form(self, owner_user_id: str) -> dict[str, Any]:
        """Return only the current owner's saved synthetic recipients for the form."""

        recipients = [
            {"id": contact["id"], "label": contact["display_name_ar"]}
            for contact in self.contacts_for_owner(owner_user_id)
        ]
        return {
            "kind": "scheduled_transfer_form",
            "data": {
                "recipients": recipients,
                "recurrence": SCHEDULE_RECURRENCE,
                "timezone": SCHEDULE_TIMEZONE,
                "authorization_mode": SCHEDULE_AUTHORIZATION_MODE,
                "execution_mode": "FRESH_PAYMENT_DRAFT_REQUIRED",
                "allowed_day_of_month": {"minimum": 1, "maximum": 28},
                "minimum_scheduled_for": utc_iso(utc_now() + SCHEDULE_MINIMUM_LEAD),
            },
        }

    def _policy(self, connection: sqlite3.Connection) -> dict[str, Any]:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = 'policy_version'"
        ).fetchone()
        return {
            "version": row["value"] if row else "mock-policy-v1",
            "transfer_fee_minor": 250,
            "bill_payment_fee_minor": 0,
        }

    @staticmethod
    def _fee_for(kind: str, policy: dict[str, Any]) -> int:
        return int(
            policy["transfer_fee_minor"]
            if kind == "transfer"
            else policy["bill_payment_fee_minor"]
        )

    @staticmethod
    def _validate_amount(amount_minor: Any, currency: Any) -> int:
        if type(amount_minor) is not int or amount_minor <= 0:
            raise WalletError(
                "INVALID_AMOUNT", "Amount must be a positive integer IQD amount."
            )
        if amount_minor > MAX_TRANSFER_MINOR:
            raise WalletError(
                "AMOUNT_LIMIT", "The synthetic demo limit is 1,000,000 IQD per payment."
            )
        if currency != "IQD":
            raise WalletError(
                "UNSUPPORTED_CURRENCY",
                "Only IQD is available in this mock-wallet demo.",
            )
        return amount_minor

    @staticmethod
    def _validate_scheduled_for(value: Any) -> str:
        if not isinstance(value, str) or not value or len(value) > 80:
            raise WalletError(
                "INVALID_SCHEDULE_TIME",
                "Choose a future date and time with an explicit UTC offset.",
            )
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise WalletError(
                "INVALID_SCHEDULE_TIME",
                "Choose a future date and time with an explicit UTC offset.",
            ) from error
        if parsed.tzinfo is None:
            raise WalletError(
                "INVALID_SCHEDULE_TIME",
                "Choose a future date and time with an explicit UTC offset.",
            )
        scheduled_for = parsed.astimezone(UTC)
        if scheduled_for <= utc_now() + SCHEDULE_MINIMUM_LEAD:
            raise ConflictError(
                "SCHEDULE_TIME_NOT_FUTURE",
                "Choose a schedule time at least five minutes in the future.",
            )
        if scheduled_for.astimezone(SCHEDULE_ZONE).day > 28:
            raise WalletError(
                "UNSUPPORTED_MONTHLY_DAY",
                "For a monthly Iraqi reminder, choose a local day from 1 through 28.",
            )
        return utc_iso(scheduled_for)

    @staticmethod
    def _validate_schedule_timezone(value: Any) -> str:
        if value != SCHEDULE_TIMEZONE:
            raise WalletError(
                "UNSUPPORTED_SCHEDULE_TIMEZONE",
                "This local Iraqi mock supports Asia/Baghdad schedule display only.",
            )
        return SCHEDULE_TIMEZONE

    @staticmethod
    def _validate_schedule_recurrence(value: Any) -> str:
        if value != SCHEDULE_RECURRENCE:
            raise WalletError(
                "UNSUPPORTED_RECURRENCE",
                "This bounded mock supports monthly reminders only.",
            )
        return SCHEDULE_RECURRENCE

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _require_current_session(
        self, connection: sqlite3.Connection, owner_user_id: str, session_id: str
    ) -> sqlite3.Row:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 200:
            raise AuthenticationError()
        session = connection.execute(
            """SELECT id, conversation_json, expires_at FROM sessions
               WHERE id = ? AND user_id = ?""",
            (session_id, owner_user_id),
        ).fetchone()
        if session is None or parse_utc(session["expires_at"]) <= utc_now():
            raise AuthenticationError(
                "This demo session has expired. Start a new demo session."
            )
        return session

    @staticmethod
    def _conversation_from_session(session: sqlite3.Row) -> dict[str, Any]:
        try:
            conversation = json.loads(session["conversation_json"])
        except (TypeError, json.JSONDecodeError):
            return {}
        return conversation if isinstance(conversation, dict) else {}

    def _set_active_review(
        self,
        connection: sqlite3.Connection,
        owner_user_id: str,
        session_id: str,
        key: str,
        review_id: str,
    ) -> None:
        session = self._require_current_session(connection, owner_user_id, session_id)
        conversation = self._conversation_from_session(session)
        conversation[key] = review_id
        connection.execute(
            "UPDATE sessions SET conversation_json = ? WHERE id = ?",
            (
                json.dumps(
                    conversation,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                session_id,
            ),
        )

    def _set_active_draft(
        self,
        connection: sqlite3.Connection,
        owner_user_id: str,
        session_id: str,
        draft_id: str,
    ) -> None:
        self._set_active_review(
            connection,
            owner_user_id,
            session_id,
            "active_draft_id",
            draft_id,
        )

    def _set_active_schedule_draft(
        self,
        connection: sqlite3.Connection,
        owner_user_id: str,
        session_id: str,
        schedule_draft_id: str,
    ) -> None:
        self._set_active_review(
            connection,
            owner_user_id,
            session_id,
            "active_schedule_draft_id",
            schedule_draft_id,
        )

    def _require_active_session_draft(
        self,
        connection: sqlite3.Connection,
        owner_user_id: str,
        session_id: str,
        draft: sqlite3.Row,
    ) -> None:
        session = self._require_current_session(connection, owner_user_id, session_id)
        if draft["issuing_session_id"] != session_id:
            raise ConflictError(
                "STALE_CONFIRMATION",
                "This review belongs to a different or expired demo session.",
            )
        conversation = self._conversation_from_session(session)
        if conversation.get("active_draft_id") != draft["id"]:
            raise ConflictError(
                "STALE_CONFIRMATION",
                "This review is no longer the active payment draft for this session.",
            )

    def _require_active_session_schedule_draft(
        self,
        connection: sqlite3.Connection,
        owner_user_id: str,
        session_id: str,
        schedule_draft: sqlite3.Row,
    ) -> None:
        session = self._require_current_session(connection, owner_user_id, session_id)
        if schedule_draft["issuing_session_id"] != session_id:
            raise ConflictError(
                "STALE_SCHEDULE_CONFIRMATION",
                "This schedule review belongs to a different or expired demo session.",
            )
        conversation = self._conversation_from_session(session)
        if conversation.get("active_schedule_draft_id") != schedule_draft["id"]:
            raise ConflictError(
                "STALE_SCHEDULE_CONFIRMATION",
                "This schedule review is no longer active for this session.",
            )

    def _clear_active_review_if_current(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        key: str,
        review_id: str,
    ) -> None:
        session = connection.execute(
            "SELECT conversation_json FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            return
        conversation = self._conversation_from_session(session)
        if conversation.get(key) != review_id:
            return
        del conversation[key]
        connection.execute(
            "UPDATE sessions SET conversation_json = ? WHERE id = ?",
            (
                json.dumps(
                    conversation,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                session_id,
            ),
        )

    def _clear_active_draft_if_current(
        self, connection: sqlite3.Connection, session_id: str, draft_id: str
    ) -> None:
        self._clear_active_review_if_current(
            connection, session_id, "active_draft_id", draft_id
        )

    def _clear_active_schedule_draft_if_current(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        schedule_draft_id: str,
    ) -> None:
        self._clear_active_review_if_current(
            connection,
            session_id,
            "active_schedule_draft_id",
            schedule_draft_id,
        )

    def _insert_draft(
        self,
        connection: sqlite3.Connection,
        *,
        owner_user_id: str,
        issuing_session_id: str,
        kind: str,
        payload: dict[str, Any],
        policy_version: str,
        now: datetime,
    ) -> IssuedDraft:
        draft_id = f"draft_{uuid4().hex}"
        token = secrets.token_urlsafe(32)
        expires_at = utc_iso(now + CONFIRMATION_LIFETIME)
        payload_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        now_iso = utc_iso(now)
        connection.execute(
            """INSERT INTO drafts
               (id, owner_user_id, issuing_session_id, kind, state, version, payload_json,
                policy_version, quote_expires_at, confirmation_token_hash,
                confirmation_expires_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'AWAITING_CONFIRMATION', 1, ?, ?, ?, ?, ?, ?, ?)""",
            (
                draft_id,
                owner_user_id,
                issuing_session_id,
                kind,
                payload_json,
                policy_version,
                expires_at,
                self._token_hash(token),
                expires_at,
                now_iso,
                now_iso,
            ),
        )
        connection.execute(
            "INSERT INTO draft_revisions(draft_id, version, payload_json, created_at) VALUES (?, 1, ?, ?)",
            (draft_id, payload_json, now_iso),
        )
        # Draft creation and the session's active-review pointer commit together,
        # so a concurrently prepared newer draft cannot leave an older approval
        # executable through a stale tab.
        self._set_active_draft(connection, owner_user_id, issuing_session_id, draft_id)
        row = connection.execute(
            "SELECT * FROM drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        return IssuedDraft(self._public_draft(self._row_or_not_found(row), now), token)

    def _insert_schedule_draft(
        self,
        connection: sqlite3.Connection,
        *,
        owner_user_id: str,
        issuing_session_id: str,
        payload: dict[str, Any],
        policy_version: str,
        now: datetime,
    ) -> IssuedScheduleDraft:
        """Create a separately-confirmed plan proposal with no ledger effect."""

        schedule_draft_id = f"schedule_draft_{uuid4().hex}"
        token = secrets.token_urlsafe(32)
        expires_at = utc_iso(now + CONFIRMATION_LIFETIME)
        payload_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        now_iso = utc_iso(now)
        connection.execute(
            """INSERT INTO schedule_drafts
               (id, owner_user_id, issuing_session_id, state, version, payload_json,
                policy_version, confirmation_token_hash, confirmation_expires_at,
                created_at, updated_at)
               VALUES (?, ?, ?, 'AWAITING_CONFIRMATION', 1, ?, ?, ?, ?, ?, ?)""",
            (
                schedule_draft_id,
                owner_user_id,
                issuing_session_id,
                payload_json,
                policy_version,
                self._token_hash(token),
                expires_at,
                now_iso,
                now_iso,
            ),
        )
        # Schedule configuration has its own active-review pointer, so it never
        # invalidates the session's separately prepared payment draft.
        self._set_active_schedule_draft(
            connection, owner_user_id, issuing_session_id, schedule_draft_id
        )
        row = connection.execute(
            "SELECT * FROM schedule_drafts WHERE id = ?", (schedule_draft_id,)
        ).fetchone()
        return IssuedScheduleDraft(
            self._public_schedule_draft(self._row_or_not_found(row), now), token
        )

    def prepare_scheduled_transfer(
        self,
        owner_user_id: str,
        issuing_session_id: str,
        recipient_id: Any,
        amount_minor: Any,
        currency: Any,
        scheduled_for: Any,
        timezone_name: Any,
        recurrence: Any,
    ) -> IssuedScheduleDraft:
        """Prepare a monthly reminder plan; it is never a future payment job."""

        amount = self._validate_amount(amount_minor, currency)
        when = self._validate_scheduled_for(scheduled_for)
        timezone_value = self._validate_schedule_timezone(timezone_name)
        recurrence_value = self._validate_schedule_recurrence(recurrence)
        if (
            not isinstance(recipient_id, str)
            or not recipient_id
            or len(recipient_id) > 100
        ):
            raise WalletError(
                "INVALID_RECIPIENT", "Choose a saved synthetic recipient."
            )
        with self._write_transaction() as connection:
            self._require_current_session(connection, owner_user_id, issuing_session_id)
            contact = connection.execute(
                """SELECT id, display_name_ar, provider, account_identifier FROM contacts
                   WHERE id = ? AND owner_user_id = ?""",
                (recipient_id, owner_user_id),
            ).fetchone()
            if contact is None:
                raise NotFoundError(
                    "RECIPIENT_NOT_FOUND",
                    "The selected recipient is unavailable in this demo account.",
                )
            policy = self._policy(connection)
            fee = self._fee_for("transfer", policy)
            payload = {
                "operation": "جدولة تذكير تحويل تجريبي",
                "recipient_id": contact["id"],
                "recipient_or_biller": contact["display_name_ar"],
                "provider": contact["provider"],
                "account_identifier": contact["account_identifier"],
                "amount_minor": amount,
                "currency": "IQD",
                "fee_minor": fee,
                "total_debit_minor": amount + fee,
                "funding_source": "رصيد المحفظة التجريبية عند إنشاء دفع جديد لاحقاً",
                "scheduled_for": when,
                "timezone": timezone_value,
                "recurrence": recurrence_value,
                "authorization_mode": SCHEDULE_AUTHORIZATION_MODE,
                "execution_mode": "FRESH_PAYMENT_DRAFT_REQUIRED",
                "warnings": [
                    "هذه جدولة تذكير تجريبية فقط؛ لا يوجد خصم أو إرسال دفع الآن أو لاحقاً تلقائياً.",
                    "كل موعد مستقبلي يحتاج مسودة دفع جديدة ومراجعة وتأكيداً نهائياً مستقلاً.",
                    "الرسوم المعروضة تقدير من سياسة العرض الحالية وليست حجزاً أو التزاماً مستقبلياً.",
                ],
            }
            return self._insert_schedule_draft(
                connection,
                owner_user_id=owner_user_id,
                issuing_session_id=issuing_session_id,
                payload=payload,
                policy_version=policy["version"],
                now=utc_now(),
            )

    def prepare_transfer(
        self,
        owner_user_id: str,
        issuing_session_id: str,
        recipient_id: Any,
        amount_minor: Any,
        currency: Any,
    ) -> IssuedDraft:
        amount = self._validate_amount(amount_minor, currency)
        if (
            not isinstance(recipient_id, str)
            or not recipient_id
            or len(recipient_id) > 100
        ):
            raise WalletError(
                "INVALID_RECIPIENT", "Choose a saved synthetic recipient."
            )
        with self._write_transaction() as connection:
            self._require_current_session(connection, owner_user_id, issuing_session_id)
            contact = connection.execute(
                """SELECT id, display_name_ar, provider, account_identifier FROM contacts
                   WHERE id = ? AND owner_user_id = ?""",
                (recipient_id, owner_user_id),
            ).fetchone()
            if contact is None:
                # Do not reveal whether the contact belongs to another demo user.
                raise NotFoundError(
                    "RECIPIENT_NOT_FOUND",
                    "The selected recipient is unavailable in this demo account.",
                )
            policy = self._policy(connection)
            fee = self._fee_for("transfer", policy)
            payload = {
                "operation": "تحويل تجريبي",
                "recipient_or_biller": contact["display_name_ar"],
                "provider": contact["provider"],
                "account_identifier": contact["account_identifier"],
                "amount_minor": amount,
                "currency": "IQD",
                "fee_minor": fee,
                "total_debit_minor": amount + fee,
                "funding_source": "رصيد المحفظة التجريبية",
                "warnings": ["مستلم تجريبي؛ راجع الاسم والمبلغ قبل التأكيد."],
            }
            return self._insert_draft(
                connection,
                owner_user_id=owner_user_id,
                issuing_session_id=issuing_session_id,
                kind="transfer",
                payload=payload,
                policy_version=policy["version"],
                now=utc_now(),
            )

    def prepare_bill_payment(
        self, owner_user_id: str, issuing_session_id: str, bill_id: Any
    ) -> IssuedDraft:
        if not isinstance(bill_id, str) or not bill_id or len(bill_id) > 100:
            raise WalletError("INVALID_BILL", "Choose a saved synthetic bill.")
        with self._write_transaction() as connection:
            self._require_current_session(connection, owner_user_id, issuing_session_id)
            bill = connection.execute(
                """SELECT biller_name, provider, account_identifier, amount_minor, currency FROM bills
                   WHERE id = ? AND owner_user_id = ?""",
                (bill_id, owner_user_id),
            ).fetchone()
            if bill is None:
                raise NotFoundError(
                    "BILL_NOT_FOUND",
                    "The selected bill is unavailable in this demo account.",
                )
            policy = self._policy(connection)
            fee = self._fee_for("bill_payment", policy)
            payload = {
                "operation": "دفع فاتورة تجريبي",
                "recipient_or_biller": bill["biller_name"],
                "provider": bill["provider"],
                "account_identifier": bill["account_identifier"],
                "amount_minor": bill["amount_minor"],
                "currency": bill["currency"],
                "fee_minor": fee,
                "total_debit_minor": bill["amount_minor"] + fee,
                "funding_source": "رصيد المحفظة التجريبية",
                "warnings": ["فاتورة تجريبية؛ المبلغ صادر من بيانات الفاتورة الوهمية."],
            }
            return self._insert_draft(
                connection,
                owner_user_id=owner_user_id,
                issuing_session_id=issuing_session_id,
                kind="bill_payment",
                payload=payload,
                policy_version=policy["version"],
                now=utc_now(),
            )

    def _owned_draft(
        self, connection: sqlite3.Connection, draft_id: str, owner_user_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM drafts WHERE id = ? AND owner_user_id = ?",
            (draft_id, owner_user_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("DRAFT_NOT_FOUND")
        return row

    def _public_draft(
        self, row: sqlite3.Row, now: datetime | None = None
    ) -> dict[str, Any]:
        current = now or utc_now()
        payload = json.loads(row["payload_json"])
        expired = parse_utc(row["quote_expires_at"]) <= current
        state = (
            "EXPIRED"
            if expired and row["state"] == "AWAITING_CONFIRMATION"
            else row["state"]
        )
        return {
            "id": row["id"],
            "kind": row["kind"],
            "state": state,
            "version": row["version"],
            "review": {
                "operation": payload["operation"],
                "recipient_or_biller": payload["recipient_or_biller"],
                "provider": payload["provider"],
                "account_identifier": payload["account_identifier"],
                "amount_minor": payload["amount_minor"],
                "currency": payload["currency"],
                "fee_minor": payload["fee_minor"],
                "total_debit_minor": payload["total_debit_minor"],
                "funding_source": payload["funding_source"],
                "quote_expires_at": row["quote_expires_at"],
                "warnings": payload["warnings"],
            },
            "can_confirm": state == "AWAITING_CONFIRMATION",
        }

    def _public_schedule_draft(
        self, row: sqlite3.Row, now: datetime | None = None
    ) -> dict[str, Any]:
        current = now or utc_now()
        payload = json.loads(row["payload_json"])
        expired = parse_utc(row["confirmation_expires_at"]) <= current
        state = (
            "EXPIRED"
            if expired and row["state"] == "AWAITING_CONFIRMATION"
            else row["state"]
        )
        return {
            "id": row["id"],
            "kind": "scheduled_transfer",
            "state": state,
            "version": row["version"],
            "review": {
                "operation": payload["operation"],
                "recipient_or_biller": payload["recipient_or_biller"],
                "provider": payload["provider"],
                "account_identifier": payload["account_identifier"],
                "amount_minor": payload["amount_minor"],
                "currency": payload["currency"],
                "fee_minor": payload["fee_minor"],
                "total_debit_minor": payload["total_debit_minor"],
                "funding_source": payload["funding_source"],
                "scheduled_for": payload["scheduled_for"],
                "timezone": payload["timezone"],
                "recurrence": payload["recurrence"],
                "authorization_mode": payload["authorization_mode"],
                "execution_mode": payload["execution_mode"],
                "quote_expires_at": row["confirmation_expires_at"],
                "confirmation_expires_at": row["confirmation_expires_at"],
                "warnings": payload["warnings"],
            },
            "can_confirm": state == "AWAITING_CONFIRMATION",
        }

    def _owned_schedule_draft(
        self,
        connection: sqlite3.Connection,
        schedule_draft_id: str,
        owner_user_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM schedule_drafts WHERE id = ? AND owner_user_id = ?",
            (schedule_draft_id, owner_user_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("SCHEDULE_DRAFT_NOT_FOUND")
        return row

    def get_schedule_draft(
        self, owner_user_id: str, schedule_draft_id: str
    ) -> dict[str, Any]:
        with self._write_transaction() as connection:
            row = self._owned_schedule_draft(
                connection, schedule_draft_id, owner_user_id
            )
            return self._public_schedule_draft(row)

    def get_draft(self, owner_user_id: str, draft_id: str) -> dict[str, Any]:
        with self._write_transaction() as connection:
            row = self._owned_draft(connection, draft_id, owner_user_id)
            return self._public_draft(row)

    def edit_draft_amount(
        self,
        owner_user_id: str,
        session_id: str,
        draft_id: str,
        amount_minor: Any,
    ) -> IssuedDraft:
        amount = self._validate_amount(amount_minor, "IQD")
        with self._write_transaction() as connection:
            row = self._owned_draft(connection, draft_id, owner_user_id)
            if row["state"] not in ("READY_FOR_REVIEW", "AWAITING_CONFIRMATION"):
                raise ConflictError(
                    "DRAFT_NOT_EDITABLE", "This draft can no longer be edited."
                )
            self._require_active_session_draft(
                connection, owner_user_id, session_id, row
            )
            payload = json.loads(row["payload_json"])
            payload["amount_minor"] = amount
            policy = self._policy(connection)
            payload["fee_minor"] = self._fee_for(row["kind"], policy)
            payload["total_debit_minor"] = amount + payload["fee_minor"]
            new_version = int(row["version"]) + 1
            now = utc_now()
            now_iso = utc_iso(now)
            expires_at = utc_iso(now + CONFIRMATION_LIFETIME)
            token = secrets.token_urlsafe(32)
            payload_json = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            connection.execute(
                """UPDATE drafts SET state = 'AWAITING_CONFIRMATION', version = ?, payload_json = ?,
                   policy_version = ?, quote_expires_at = ?, confirmation_token_hash = ?,
                   confirmation_expires_at = ?, updated_at = ? WHERE id = ?""",
                (
                    new_version,
                    payload_json,
                    policy["version"],
                    expires_at,
                    self._token_hash(token),
                    expires_at,
                    now_iso,
                    draft_id,
                ),
            )
            connection.execute(
                "INSERT INTO draft_revisions(draft_id, version, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (draft_id, new_version, payload_json, now_iso),
            )
            self._set_active_draft(connection, owner_user_id, session_id, draft_id)
            updated = connection.execute(
                "SELECT * FROM drafts WHERE id = ?", (draft_id,)
            ).fetchone()
            return IssuedDraft(
                self._public_draft(self._row_or_not_found(updated), now), token
            )

    def cancel_draft(
        self, owner_user_id: str, session_id: str, draft_id: str
    ) -> dict[str, Any]:
        with self._write_transaction() as connection:
            self._require_current_session(connection, owner_user_id, session_id)
            row = self._owned_draft(connection, draft_id, owner_user_id)
            if row["state"] in ("SUCCEEDED", "FAILED", "UNKNOWN"):
                raise ConflictError(
                    "DRAFT_FINAL", "A finalised draft cannot be cancelled."
                )
            now_iso = utc_iso()
            connection.execute(
                """UPDATE drafts SET state = 'CANCELLED', version = version + 1,
                   confirmation_token_hash = NULL, confirmation_expires_at = ?,
                   cancelled_at = ?, updated_at = ? WHERE id = ?""",
                (now_iso, now_iso, now_iso, draft_id),
            )
            self._clear_active_draft_if_current(connection, session_id, draft_id)
            updated = connection.execute(
                "SELECT * FROM drafts WHERE id = ?", (draft_id,)
            ).fetchone()
            return self._public_draft(self._row_or_not_found(updated))

    def _public_schedule(
        self, row: sqlite3.Row, *, duplicate: bool = False
    ) -> dict[str, Any]:
        return {
            "id": row["id"],
            "schedule_draft_id": row["schedule_draft_id"],
            "status": row["status"],
            "recipient_or_biller": row["recipient_or_biller"],
            "provider": row["provider"],
            "account_identifier": row["account_identifier"],
            "scheduled_for": row["scheduled_for"],
            "timezone": row["timezone"],
            "recurrence": row["recurrence"],
            "authorization_mode": row["authorization_mode"],
            "execution_mode": "FRESH_PAYMENT_DRAFT_REQUIRED",
            "requires_fresh_payment_draft": True,
            "amount_minor": row["amount_minor"],
            "fee_minor": row["fee_minor"],
            "estimated_total_minor": row["total_debit_minor"],
            "debit_minor": 0,
            "currency": row["currency"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "duplicate": duplicate,
            "note": (
                "Mock schedule configuration only. No payment, reserve, timer, "
                "or notification was created; every future payment needs a fresh "
                "review and final confirmation."
            ),
        }

    def cancel_schedule_draft(
        self, owner_user_id: str, session_id: str, schedule_draft_id: str
    ) -> dict[str, Any]:
        with self._write_transaction() as connection:
            self._require_current_session(connection, owner_user_id, session_id)
            row = self._owned_schedule_draft(
                connection, schedule_draft_id, owner_user_id
            )
            if row["state"] == "SCHEDULED_MOCK_ONLY":
                raise ConflictError(
                    "SCHEDULE_DRAFT_FINAL",
                    "This schedule configuration is already finalised in the local mock.",
                )
            if row["state"] == "CANCELLED":
                return self._public_schedule_draft(row)
            now_iso = utc_iso()
            connection.execute(
                """UPDATE schedule_drafts SET state = 'CANCELLED', version = version + 1,
                   confirmation_token_hash = NULL, confirmation_expires_at = ?,
                   cancelled_at = ?, updated_at = ? WHERE id = ?""",
                (now_iso, now_iso, now_iso, schedule_draft_id),
            )
            self._clear_active_schedule_draft_if_current(
                connection, session_id, schedule_draft_id
            )
            updated = connection.execute(
                "SELECT * FROM schedule_drafts WHERE id = ?", (schedule_draft_id,)
            ).fetchone()
            return self._public_schedule_draft(self._row_or_not_found(updated))

    def confirm_schedule_draft(
        self,
        owner_user_id: str,
        session_id: str,
        schedule_draft_id: str,
        confirmation_token: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Persist one mock reminder configuration without invoking payment logic."""

        with self._write_transaction() as connection:
            row = self._owned_schedule_draft(
                connection, schedule_draft_id, owner_user_id
            )
            existing = connection.execute(
                "SELECT * FROM scheduled_payment_plans WHERE schedule_draft_id = ?",
                (schedule_draft_id,),
            ).fetchone()
            if existing is not None:
                return self._public_schedule_draft(row), self._public_schedule(
                    existing, duplicate=True
                )
            if row["state"] == "CANCELLED":
                raise ConflictError(
                    "SCHEDULE_DRAFT_CANCELLED",
                    "This schedule draft was cancelled and its confirmation is invalid.",
                )
            if row["state"] == "EXPIRED":
                raise ConflictError(
                    "SCHEDULE_DRAFT_EXPIRED",
                    "This schedule review expired. Prepare a fresh schedule draft.",
                )
            if row["state"] != "AWAITING_CONFIRMATION":
                raise ConflictError(
                    "SCHEDULE_DRAFT_NOT_CONFIRMABLE",
                    "This schedule draft is not awaiting confirmation.",
                )
            self._require_active_session_schedule_draft(
                connection, owner_user_id, session_id, row
            )
            now = utc_now()
            if parse_utc(row["confirmation_expires_at"]) <= now:
                connection.execute(
                    """UPDATE schedule_drafts SET state = 'EXPIRED',
                       confirmation_token_hash = NULL, updated_at = ? WHERE id = ?""",
                    (utc_iso(now), schedule_draft_id),
                )
                self._clear_active_schedule_draft_if_current(
                    connection, session_id, schedule_draft_id
                )
                raise ConflictError(
                    "SCHEDULE_DRAFT_EXPIRED",
                    "This schedule review expired. Prepare a fresh schedule draft.",
                )
            if not confirmation_token or not row["confirmation_token_hash"]:
                raise ForbiddenError(
                    "Use the final Confirm button from the current schedule review card."
                )
            if not hmac.compare_digest(
                row["confirmation_token_hash"], self._token_hash(confirmation_token)
            ):
                raise ConflictError(
                    "STALE_SCHEDULE_CONFIRMATION",
                    "This confirmation belongs to an older or changed schedule review.",
                )
            policy = self._policy(connection)
            if policy["version"] != row["policy_version"]:
                raise ConflictError(
                    "STALE_POLICY",
                    "Policy changed; refresh the schedule draft before confirming.",
                )
            payload = json.loads(row["payload_json"])
            expected_fee = self._fee_for("transfer", policy)
            if (
                payload.get("fee_minor") != expected_fee
                or payload.get("total_debit_minor")
                != payload.get("amount_minor", 0) + expected_fee
            ):
                raise ConflictError(
                    "STALE_QUOTE",
                    "The displayed schedule estimate is no longer current. Refresh it first.",
                )
            if (
                payload.get("timezone") != SCHEDULE_TIMEZONE
                or payload.get("recurrence") != SCHEDULE_RECURRENCE
                or payload.get("authorization_mode") != SCHEDULE_AUTHORIZATION_MODE
                or payload.get("execution_mode") != "FRESH_PAYMENT_DRAFT_REQUIRED"
            ):
                raise ConflictError(
                    "SCHEDULE_DETAILS_INVALID",
                    "The schedule details are no longer valid. Prepare a fresh review.",
                )
            try:
                scheduled_for = parse_utc(str(payload["scheduled_for"]))
            except (KeyError, TypeError, ValueError) as error:
                raise ConflictError(
                    "SCHEDULE_DETAILS_INVALID",
                    "The schedule time is invalid. Prepare a fresh review.",
                ) from error
            if scheduled_for <= now:
                raise ConflictError(
                    "SCHEDULE_TIME_PASSED",
                    "The selected schedule time has passed. Prepare a fresh review.",
                )
            schedule_id = f"schedule_{uuid4().hex}"
            now_iso = utc_iso(now)
            connection.execute(
                """INSERT INTO scheduled_payment_plans
                   (id, schedule_draft_id, owner_user_id, recipient_id,
                    recipient_or_biller, provider, account_identifier, status,
                    scheduled_for, timezone, recurrence, authorization_mode,
                    amount_minor, fee_minor, total_debit_minor, currency,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE_MOCK_ONLY', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    schedule_id,
                    schedule_draft_id,
                    owner_user_id,
                    payload["recipient_id"],
                    payload["recipient_or_biller"],
                    payload["provider"],
                    payload["account_identifier"],
                    payload["scheduled_for"],
                    payload["timezone"],
                    payload["recurrence"],
                    payload["authorization_mode"],
                    payload["amount_minor"],
                    payload["fee_minor"],
                    payload["total_debit_minor"],
                    payload["currency"],
                    now_iso,
                    now_iso,
                ),
            )
            # This table is intentionally the only effect of a schedule
            # confirmation. It does not query or update account balances and
            # cannot create a transaction record.
            connection.execute(
                """UPDATE schedule_drafts SET state = 'SCHEDULED_MOCK_ONLY',
                   confirmation_token_hash = NULL, updated_at = ? WHERE id = ?""",
                (now_iso, schedule_draft_id),
            )
            self._clear_active_schedule_draft_if_current(
                connection, session_id, schedule_draft_id
            )
            updated_draft = connection.execute(
                "SELECT * FROM schedule_drafts WHERE id = ?", (schedule_draft_id,)
            ).fetchone()
            schedule = connection.execute(
                "SELECT * FROM scheduled_payment_plans WHERE id = ?", (schedule_id,)
            ).fetchone()
            return (
                self._public_schedule_draft(self._row_or_not_found(updated_draft), now),
                self._public_schedule(self._row_or_not_found(schedule)),
            )

    def _public_transaction(
        self, row: sqlite3.Row, *, duplicate: bool = False
    ) -> dict[str, Any]:
        receipt = json.loads(row["receipt_json"]) if row["receipt_json"] else None
        status = row["status"]
        recovery_message = {
            "SUCCEEDED": "تم العثور على نتيجة العملية المخزنة؛ لم يتم إرسال دفع جديد.",
            "UNKNOWN": "الحالة غير معروفة لدى الخدمة التجريبية. تحقق من هذا السجل نفسه؛ لا تعيد الدفع.",
            "FAILED": "هذه العملية فشلت في السجل التجريبي ولم تخصم رصيداً جديداً.",
        }[status]
        return {
            "id": row["id"],
            "draft_id": row["draft_id"],
            "kind": row["kind"],
            "status": status,
            "debit_minor": row["debit_minor"],
            "currency": row["currency"],
            "counterparty": row["counterparty"],
            "provider": row["provider"],
            "reference": row["reference"],
            "receipt": receipt,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "duplicate": duplicate,
            "recovery_message": recovery_message,
        }

    def confirm_draft(
        self,
        owner_user_id: str,
        session_id: str,
        draft_id: str,
        confirmation_token: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Commit exactly one mock debit for an owner-bound reviewed draft.

        SQLite's immediate transaction and ``transactions.draft_id UNIQUE`` make
        retry/double-tap responses converge on the stored receipt.
        """

        with self._write_transaction() as connection:
            row = self._owned_draft(connection, draft_id, owner_user_id)
            existing = connection.execute(
                "SELECT * FROM transactions WHERE draft_id = ?", (draft_id,)
            ).fetchone()
            if existing is not None:
                return self._public_draft(row), self._public_transaction(
                    existing, duplicate=True
                )
            if row["state"] == "CANCELLED":
                raise ConflictError(
                    "DRAFT_CANCELLED",
                    "This draft was cancelled and its confirmation is invalid.",
                )
            if row["state"] == "EXPIRED":
                raise ConflictError(
                    "DRAFT_EXPIRED",
                    "This review expired. Prepare a fresh draft before confirming.",
                )
            if row["state"] != "AWAITING_CONFIRMATION":
                raise ConflictError(
                    "DRAFT_NOT_CONFIRMABLE", "This draft is not awaiting confirmation."
                )
            self._require_active_session_draft(
                connection, owner_user_id, session_id, row
            )
            now = utc_now()
            if (
                parse_utc(row["quote_expires_at"]) <= now
                or parse_utc(row["confirmation_expires_at"]) <= now
            ):
                connection.execute(
                    """UPDATE drafts SET state = 'EXPIRED', confirmation_token_hash = NULL,
                       updated_at = ? WHERE id = ?""",
                    (utc_iso(now), draft_id),
                )
                self._clear_active_draft_if_current(connection, session_id, draft_id)
                connection.commit()
                raise ConflictError(
                    "DRAFT_EXPIRED",
                    "This review expired. Prepare a fresh draft before confirming.",
                )
            if not confirmation_token or not row["confirmation_token_hash"]:
                raise ForbiddenError(
                    "Use the final Confirm button from the current review card."
                )
            if not hmac.compare_digest(
                row["confirmation_token_hash"], self._token_hash(confirmation_token)
            ):
                raise ConflictError(
                    "STALE_CONFIRMATION",
                    "This confirmation belongs to an older or changed review.",
                )
            policy = self._policy(connection)
            if policy["version"] != row["policy_version"]:
                raise ConflictError(
                    "STALE_POLICY",
                    "Policy changed; refresh the draft before confirming.",
                )
            payload = json.loads(row["payload_json"])
            expected_fee = self._fee_for(row["kind"], policy)
            if (
                payload["fee_minor"] != expected_fee
                or payload["total_debit_minor"]
                != payload["amount_minor"] + expected_fee
            ):
                raise ConflictError(
                    "STALE_QUOTE",
                    "The quote is no longer current. Refresh the draft before confirming.",
                )
            account = connection.execute(
                "SELECT available_minor, currency FROM accounts WHERE user_id = ?",
                (owner_user_id,),
            ).fetchone()
            account = self._row_or_not_found(account, "ACCOUNT_NOT_FOUND")
            if account["currency"] != payload["currency"]:
                raise ConflictError(
                    "ACCOUNT_CURRENCY_CHANGED",
                    "The funding account no longer matches this draft.",
                )
            total = int(payload["total_debit_minor"])
            if account["available_minor"] < total:
                raise ConflictError(
                    "INSUFFICIENT_BALANCE",
                    "The current wallet balance cannot cover this payment.",
                )
            debit = connection.execute(
                """UPDATE accounts SET available_minor = available_minor - ?
                   WHERE user_id = ? AND available_minor >= ?""",
                (total, owner_user_id, total),
            )
            if debit.rowcount != 1:
                # Defensive guard if a future refactor changes the transaction lock.
                raise ConflictError(
                    "INSUFFICIENT_BALANCE",
                    "The current wallet balance cannot cover this payment.",
                )
            transaction_id = f"txn_{uuid4().hex}"
            reference = f"MOCK-{uuid4().hex[:12].upper()}"
            now_iso = utc_iso(now)
            receipt = {
                "receipt_type": "mock_wallet_receipt",
                "transaction_id": transaction_id,
                "reference": reference,
                "operation": payload["operation"],
                "total_debit_minor": total,
                "currency": payload["currency"],
                "completed_at": now_iso,
                "note": "Synthetic local mock service. No real payment was sent.",
            }
            connection.execute(
                """INSERT INTO transactions
                   (id, draft_id, owner_user_id, kind, status, debit_minor, currency, counterparty,
                    provider, reference, receipt_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'SUCCEEDED', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    transaction_id,
                    draft_id,
                    owner_user_id,
                    row["kind"],
                    total,
                    payload["currency"],
                    payload["recipient_or_biller"],
                    payload["provider"],
                    reference,
                    json.dumps(receipt, ensure_ascii=False, sort_keys=True),
                    now_iso,
                    now_iso,
                ),
            )
            connection.execute(
                """INSERT INTO provider_results(transaction_id, status, receipt_json, updated_at)
                   VALUES (?, 'SUCCEEDED', ?, ?)""",
                (
                    transaction_id,
                    json.dumps(receipt, ensure_ascii=False, sort_keys=True),
                    now_iso,
                ),
            )
            connection.execute(
                """UPDATE drafts SET state = 'SUCCEEDED', confirmation_token_hash = NULL,
                   updated_at = ? WHERE id = ?""",
                (now_iso, draft_id),
            )
            self._clear_active_draft_if_current(connection, session_id, draft_id)
            updated = connection.execute(
                "SELECT * FROM drafts WHERE id = ?", (draft_id,)
            ).fetchone()
            transaction = connection.execute(
                "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
            ).fetchone()
            return (
                self._public_draft(self._row_or_not_found(updated), now),
                self._public_transaction(self._row_or_not_found(transaction)),
            )

    def get_transaction_status(
        self, owner_user_id: str, transaction_identifier: str
    ) -> dict[str, Any]:
        if (
            not isinstance(transaction_identifier, str)
            or not transaction_identifier
            or len(transaction_identifier) > 100
        ):
            raise NotFoundError("TRANSACTION_NOT_FOUND")
        # Receipt references are safe to display in the UI; internal transaction
        # IDs serve direct status routes. Both resolve only inside the current
        # owner scope and each maps to a unique stored transaction.
        with self._write_transaction() as connection:
            row = connection.execute(
                """SELECT * FROM transactions
                   WHERE owner_user_id = ? AND (id = ? OR reference = ?)""",
                (owner_user_id, transaction_identifier, transaction_identifier),
            ).fetchone()
            if row is None:
                raise NotFoundError("TRANSACTION_NOT_FOUND")
            transaction_id = row["id"]
            if row["status"] == "UNKNOWN":
                provider_result = connection.execute(
                    "SELECT status, receipt_json, updated_at FROM provider_results WHERE transaction_id = ?",
                    (transaction_id,),
                ).fetchone()
                if (
                    provider_result is not None
                    and provider_result["status"] == "SUCCEEDED"
                ):
                    connection.execute(
                        """UPDATE transactions SET status = 'SUCCEEDED', receipt_json = ?, updated_at = ?
                           WHERE id = ?""",
                        (
                            provider_result["receipt_json"],
                            provider_result["updated_at"],
                            transaction_id,
                        ),
                    )
                    row = connection.execute(
                        "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
                    ).fetchone()
            return self._public_transaction(self._row_or_not_found(row))

    def get_draft_status(self, owner_user_id: str, draft_id: str) -> dict[str, Any]:
        """Recover the exact original action from its owner-bound draft ID."""
        draft = self.get_draft(owner_user_id, draft_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT id FROM transactions WHERE draft_id = ? AND owner_user_id = ?",
                (draft_id, owner_user_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return {
                "draft": draft,
                "transaction": None,
                "recovery_message": "لا توجد عملية مرسلة لهذه المسودة؛ لا تعيد الدفع قبل مراجعة الحالة.",
            }
        transaction = self.get_transaction_status(owner_user_id, row["id"])
        return {
            "draft": self.get_draft(owner_user_id, draft_id),
            "transaction": transaction,
            "recovery_message": transaction["recovery_message"],
        }

    def get_schedule_draft_status(
        self, owner_user_id: str, schedule_draft_id: str
    ) -> dict[str, Any]:
        """Recover a stored mock schedule configuration without creating payment."""

        draft = self.get_schedule_draft(owner_user_id, schedule_draft_id)
        connection = self._connect()
        try:
            row = connection.execute(
                """SELECT * FROM scheduled_payment_plans
                   WHERE schedule_draft_id = ? AND owner_user_id = ?""",
                (schedule_draft_id, owner_user_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return {
                "schedule_draft": draft,
                "schedule": None,
                "recovery_message": (
                    "لا يوجد جدول محفوظ لهذه المسودة؛ لا توجد أي دفعة مرسلة أو محجوزة."
                ),
            }
        schedule = self._public_schedule(row)
        return {
            "schedule_draft": self.get_schedule_draft(owner_user_id, schedule_draft_id),
            "schedule": schedule,
            "recovery_message": schedule["note"],
        }

    def operator_issues_view(self, role: str) -> dict[str, Any]:
        if role != "operator":
            raise ForbiddenError()
        return {
            "kind": "operator_issues",
            "items": [],
            "note": "No customer records are exposed in this local mock operator view.",
        }

    # Test-only support: it is deliberately not routed through HTTP.  It models a
    # provider timeout after a durable local transaction record and lets status
    # recovery be tested without fabricating a second debit.
    def _mark_transaction_unknown_for_test(self, transaction_id: str) -> None:
        with self._write_transaction() as connection:
            connection.execute(
                "UPDATE transactions SET status = 'UNKNOWN', receipt_json = NULL, updated_at = ? WHERE id = ?",
                (utc_iso(), transaction_id),
            )

    def _set_policy_version_for_test(self, value: str) -> None:
        with self._write_transaction() as connection:
            connection.execute(
                "UPDATE settings SET value = ? WHERE key = 'policy_version'", (value,)
            )

    def _expire_draft_for_test(self, draft_id: str) -> None:
        past = utc_iso(utc_now() - timedelta(seconds=1))
        with self._write_transaction() as connection:
            connection.execute(
                """UPDATE drafts SET quote_expires_at = ?, confirmation_expires_at = ? WHERE id = ?""",
                (past, past, draft_id),
            )

    def _expire_schedule_draft_for_test(self, schedule_draft_id: str) -> None:
        """Test-only expiry fixture; no schedule execution code exists."""

        past = utc_iso(utc_now() - timedelta(seconds=1))
        with self._write_transaction() as connection:
            connection.execute(
                """UPDATE schedule_drafts SET confirmation_expires_at = ? WHERE id = ?""",
                (past, schedule_draft_id),
            )
