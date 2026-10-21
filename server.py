"""Local HTTP boundary for the READY / ZainCash safe-core mock demo.

Run with ``python server.py`` and open http://127.0.0.1:8765.  The service is
strictly local, uses only SQLite fixtures, and makes no external model or
payment calls.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import re
import socket
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse, urlsplit

from action_registry import actions_for_role, get_action
from agent import route_chat
from core import (
    ForbiddenError,
    IssuedDraft,
    IssuedScheduleDraft,
    MockWallet,
    WalletError,
)

MAX_BODY_BYTES = 16_384
MAX_MESSAGE_CHARS = 500
_DRAFT_CONFIRM_RE = re.compile(r"^/api/drafts/(draft_[A-Za-z0-9]+)/confirm$")
_DRAFT_CANCEL_RE = re.compile(r"^/api/drafts/(draft_[A-Za-z0-9]+)/cancel$")
_DRAFT_STATUS_RE = re.compile(r"^/api/drafts/(draft_[A-Za-z0-9]+)/status$")
_SCHEDULE_DRAFT_CONFIRM_RE = re.compile(
    r"^/api/schedule-drafts/(schedule_draft_[A-Za-z0-9]+)/confirm$"
)
_SCHEDULE_DRAFT_CANCEL_RE = re.compile(
    r"^/api/schedule-drafts/(schedule_draft_[A-Za-z0-9]+)/cancel$"
)
_SCHEDULE_DRAFT_STATUS_RE = re.compile(
    r"^/api/schedule-drafts/(schedule_draft_[A-Za-z0-9]+)/status$"
)
_TRANSACTION_STATUS_RE = re.compile(r"^/api/transactions/(txn_[A-Za-z0-9_]+)/status$")
_ACTION_RE = re.compile(r"^/api/actions/([A-Z_]+)$")


def _loopback_ip(value: object) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return a literal loopback address, never resolving an untrusted name."""
    if not isinstance(value, str) or not value or "%" in value:
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return None
    return address if address.is_loopback else None


def resolve_loopback_bind_host(host: str) -> str:
    """Resolve a permitted bind host once, then bind only to its literal IP.

    ``localhost`` is retained as a convenient explicit local alias, but every
    result must be loopback. Binding the returned literal prevents a later DNS
    or hosts-file change from changing the effective listening address.
    """
    if not isinstance(host, str) or not host or host != host.strip():
        raise ValueError("host must be a loopback IP address or localhost")
    literal = _loopback_ip(host)
    if literal is not None:
        return str(literal)
    if host.lower() != "localhost":
        raise ValueError("host must be a loopback IP address or localhost")
    try:
        results = socket.getaddrinfo(
            host, 0, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
    except socket.gaierror as error:
        raise ValueError(
            "localhost could not be resolved to a loopback address"
        ) from error
    resolved: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for family, _socktype, _protocol, _canonical_name, sockaddr in results:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            raise ValueError("localhost resolved to an unsupported address family")
        address = _loopback_ip(sockaddr[0])
        if address is None:
            raise ValueError("localhost must resolve exclusively to loopback addresses")
        resolved.append(address)
    if not resolved:
        raise ValueError("localhost did not resolve to a loopback address")
    # Prefer IPv4 for broad local development compatibility; either candidate
    # remains a verified literal loopback address.
    resolved.sort(key=lambda address: (address.version != 4, str(address)))
    return str(resolved[0])


def is_loopback_peer_address(client_address: object) -> bool:
    """Check the kernel-supplied peer address independently of HTTP headers."""
    return (
        isinstance(client_address, tuple)
        and bool(client_address)
        and _loopback_ip(client_address[0]) is not None
    )


def is_local_host_authority(authority: str | None) -> bool:
    """Accept only a syntactically valid localhost/loopback Host authority."""
    if not isinstance(authority, str) or not authority or len(authority) > 255:
        return False
    if any(character in authority for character in " \t\r\n/@?#\\,%"):
        return False
    host: str
    port_text = ""
    has_port = False
    if authority.startswith("["):
        closing = authority.find("]")
        if closing <= 1:
            return False
        host = authority[1:closing]
        remainder = authority[closing + 1 :]
        if remainder:
            if not remainder.startswith(":"):
                return False
            has_port = True
            port_text = remainder[1:]
    else:
        if authority.count(":") > 1:
            return False  # IPv6 Host headers must use brackets.
        if ":" in authority:
            host, port_text = authority.rsplit(":", 1)
            has_port = True
        else:
            host = authority
    if not host:
        return False
    if has_port:
        if not port_text or not port_text.isascii() or not port_text.isdecimal():
            return False
        port = int(port_text)
        if not 1 <= port <= 65_535:
            return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_local_origin(origin: str | None) -> bool:
    """Validate a browser Origin without permitting hostname suffix tricks."""
    if not isinstance(origin, str) or not origin or len(origin) > 512:
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and not parsed.username
        and not parsed.password
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and is_local_host_authority(parsed.netloc)
    )


class DemoApp:
    """Coordinates deterministic chat with the server-owned domain layer."""

    def __init__(self, database_path: str | Path) -> None:
        self.wallet = MockWallet(database_path)

    @staticmethod
    def _require_customer(session: dict[str, str]) -> None:
        if session["role"] != "customer":
            raise ForbiddenError("Only a demo customer can access mock-wallet actions.")

    def bootstrap(self, user_id: str) -> dict[str, Any]:
        session = self.wallet.create_demo_session(user_id)
        user = self.wallet.get_user(session["user_id"])
        payload: dict[str, Any] = {
            "mock": True,
            "session": session,
            "user": user,
            "actions": actions_for_role(session["role"]),
            "messages": [
                {
                    "role": "assistant",
                    "text": "هذا عرض محفظة تجريبي ببيانات خيالية؛ لا توجد أي خدمة دفع أو نموذج خارجي متصل.",
                }
            ],
        }
        if session["role"] == "customer":
            payload["balance"] = self.wallet.get_balance(session["user_id"])
            payload["view"] = {"kind": "balance", "data": payload["balance"]}
            payload["schedule_transfer_form"] = self.wallet.get_schedule_transfer_form(
                session["user_id"]
            )
        return payload

    def dispatch_action(
        self, session: dict[str, str], action_id: str, body: dict[str, Any]
    ) -> tuple[dict[str, Any], IssuedDraft | IssuedScheduleDraft | None]:
        action = get_action(action_id)
        if action is None:
            raise WalletError(
                "UNKNOWN_ACTION", "That action is not registered for this demo."
            )
        if session["role"] not in action.roles:
            raise ForbiddenError()
        self._validate_action_body(action_id, body, action.parameters)
        owner = session["user_id"]
        public_action = action.public()
        if action_id == "SHOW_RECEIVE_QR":
            return {
                "action": public_action,
                "view": {
                    "kind": "receive_qr",
                    "data": self.wallet.get_receive_qr(owner),
                },
            }, None
        if action_id == "VIEW_BALANCE":
            return {
                "action": public_action,
                "view": {"kind": "balance", "data": self.wallet.get_balance(owner)},
            }, None
        if action_id == "VIEW_HISTORY":
            return {
                "action": public_action,
                "view": {"kind": "history", "data": self.wallet.get_history(owner)},
            }, None
        if action_id == "OPEN_TRANSFER":
            issued = self.wallet.prepare_transfer(
                owner,
                session["id"],
                body["recipient_id"],
                body["amount_minor"],
                body["currency"],
            )
            return {
                "action": public_action,
                "draft": issued.draft,
                "messages": [
                    {
                        "role": "assistant",
                        "text": "راجع التفاصيل ثم استخدم زر التأكيد النهائي.",
                    }
                ],
            }, issued
        if action_id == "OPEN_SCHEDULED_TRANSFER":
            issued = self.wallet.prepare_scheduled_transfer(
                owner,
                session["id"],
                body["recipient_id"],
                body["amount_minor"],
                body["currency"],
                body["scheduled_for"],
                body["timezone"],
                body["recurrence"],
            )
            return {
                "action": public_action,
                "schedule_draft": issued.schedule_draft,
                "messages": [
                    {
                        "role": "assistant",
                        "text": (
                            "راجع جدول التذكير الشهري. التأكيد يحفظ إعداداً محلياً فقط "
                            "ولا ينشئ أي دفعة أو خصم تلقائي."
                        ),
                    }
                ],
            }, issued
        if action_id == "OPEN_BILL_PAYMENT":
            issued = self.wallet.prepare_bill_payment(
                owner, session["id"], body["bill_id"]
            )
            return {
                "action": public_action,
                "draft": issued.draft,
                "messages": [
                    {
                        "role": "assistant",
                        "text": "راجع تفاصيل الفاتورة ثم استخدم زر التأكيد النهائي.",
                    }
                ],
            }, issued
        if action_id == "CHECK_PAYMENT_STATUS":
            transaction = self.wallet.get_transaction_status(
                owner, body["transaction_id"]
            )
            return {
                "action": public_action,
                "view": {"kind": "payment_status", "data": transaction},
            }, None
        if action_id == "VIEW_OPERATOR_ISSUES":
            view = self.wallet.operator_issues_view(session["role"])
            return {
                "action": public_action,
                "view": {"kind": view["kind"], "data": view},
            }, None
        # The registry and dispatch table are intentionally closed together.
        raise WalletError(
            "UNSUPPORTED_ACTION", "That registered action has no local demo handler."
        )

    @staticmethod
    def _validate_action_body(
        action_id: str, body: dict[str, Any], parameters: dict[str, type] | Any
    ) -> None:
        expected = set(parameters)
        actual = set(body)
        if actual != expected:
            raise WalletError(
                "INVALID_ACTION_PARAMETERS",
                f"{action_id} requires exactly: {', '.join(sorted(expected)) or 'no parameters'}.",
            )
        for key, expected_type in parameters.items():
            value = body[key]
            if expected_type is int:
                valid = type(value) is int
            else:
                valid = isinstance(value, expected_type)
            if not valid:
                raise WalletError(
                    "INVALID_ACTION_PARAMETERS", f"{key} has an invalid type."
                )

    def chat(
        self, session: dict[str, str], message: str
    ) -> tuple[dict[str, Any], IssuedDraft | IssuedScheduleDraft | None]:
        self._require_customer(session)
        if (
            not isinstance(message, str)
            or not message.strip()
            or len(message) > MAX_MESSAGE_CHARS
        ):
            raise WalletError(
                "INVALID_MESSAGE", "Message must be between 1 and 500 characters."
            )
        conversation = self.wallet.get_conversation(session["id"])
        decision = route_chat(
            message,
            conversation,
            self.wallet.contacts_for_owner(session["user_id"]),
            self.wallet.bills_for_owner(session["user_id"]),
        )
        response: dict[str, Any] = {
            "messages": [{"role": "assistant", "text": decision.text}],
            "actions": [],
        }
        issued: IssuedDraft | IssuedScheduleDraft | None = None
        next_conversation = decision.conversation or {}
        if decision.kind == "view":
            assert decision.action_id is not None
            action_response, _ = self.dispatch_action(session, decision.action_id, {})
            response["actions"] = [action_response["action"]]
            response["view"] = action_response["view"]
        elif decision.kind == "clarification":
            response["clarification"] = decision.clarification
        elif decision.kind == "open_schedule_form":
            assert decision.action_id == "OPEN_SCHEDULED_TRANSFER"
            response["actions"] = [get_action(decision.action_id).public()]
            response["view"] = self.wallet.get_schedule_transfer_form(
                session["user_id"]
            )
        elif decision.kind == "prepare_transfer":
            assert (
                decision.recipient_id is not None and decision.amount_minor is not None
            )
            action_response, issued = self.dispatch_action(
                session,
                "OPEN_TRANSFER",
                {
                    "recipient_id": decision.recipient_id,
                    "amount_minor": decision.amount_minor,
                    "currency": "IQD",
                },
            )
            response["actions"] = [action_response["action"]]
            response["draft"] = issued.draft
            next_conversation = {"active_draft_id": issued.draft["id"]}
        elif decision.kind == "prepare_bill":
            assert decision.bill_id is not None
            action_response, issued = self.dispatch_action(
                session, "OPEN_BILL_PAYMENT", {"bill_id": decision.bill_id}
            )
            response["actions"] = [action_response["action"]]
            response["draft"] = issued.draft
            next_conversation = {"active_draft_id": issued.draft["id"]}
        elif decision.kind == "edit_draft_amount":
            active_draft_id = conversation.get("active_draft_id")
            if not isinstance(active_draft_id, str) or decision.amount_minor is None:
                raise WalletError(
                    "NO_ACTIVE_DRAFT", "There is no review draft to edit."
                )
            issued = self.wallet.edit_draft_amount(
                session["user_id"],
                session["id"],
                active_draft_id,
                decision.amount_minor,
            )
            response["draft"] = issued.draft
            response["actions"] = [
                get_action("OPEN_TRANSFER").public()
            ]  # known registered UI action
            next_conversation = {"active_draft_id": issued.draft["id"]}
        if issued is None:
            self.wallet.set_conversation(session["id"], next_conversation)
        return response, issued

    def cancel_draft(self, session: dict[str, str], draft_id: str) -> dict[str, Any]:
        self._require_customer(session)
        draft = self.wallet.cancel_draft(session["user_id"], session["id"], draft_id)
        return {
            "draft": draft,
            "message": "تم إلغاء المسودة التجريبية؛ لن ينفذ التأكيد السابق.",
        }

    def confirm_draft(
        self, session: dict[str, str], draft_id: str, confirmation_token: str | None
    ) -> dict[str, Any]:
        self._require_customer(session)
        draft, transaction = self.wallet.confirm_draft(
            session["user_id"], session["id"], draft_id, confirmation_token
        )
        return {"draft": draft, "transaction": transaction}

    def draft_status(self, session: dict[str, str], draft_id: str) -> dict[str, Any]:
        self._require_customer(session)
        return self.wallet.get_draft_status(session["user_id"], draft_id)

    def cancel_schedule_draft(
        self, session: dict[str, str], schedule_draft_id: str
    ) -> dict[str, Any]:
        self._require_customer(session)
        schedule_draft = self.wallet.cancel_schedule_draft(
            session["user_id"], session["id"], schedule_draft_id
        )
        return {
            "schedule_draft": schedule_draft,
            "message": "تم إلغاء مسودة الجدولة التجريبية؛ لن ينفذ التأكيد السابق.",
        }

    def confirm_schedule_draft(
        self,
        session: dict[str, str],
        schedule_draft_id: str,
        confirmation_token: str | None,
    ) -> dict[str, Any]:
        self._require_customer(session)
        schedule_draft, schedule = self.wallet.confirm_schedule_draft(
            session["user_id"],
            session["id"],
            schedule_draft_id,
            confirmation_token,
        )
        return {"schedule_draft": schedule_draft, "schedule": schedule}

    def schedule_draft_status(
        self, session: dict[str, str], schedule_draft_id: str
    ) -> dict[str, Any]:
        self._require_customer(session)
        return self.wallet.get_schedule_draft_status(
            session["user_id"], schedule_draft_id
        )


def confirmation_cookie_name(draft_id: str) -> str:
    return f"ready_confirm_{draft_id}"


def confirmation_cookie(draft_id: str, token: str, *, clear: bool = False) -> str:
    cookie = SimpleCookie()
    name = confirmation_cookie_name(draft_id)
    cookie[name] = "" if clear else token
    morsel = cookie[name]
    morsel["path"] = f"/api/drafts/{draft_id}/confirm"
    morsel["httponly"] = True
    morsel["samesite"] = "Strict"
    if clear:
        morsel["max-age"] = 0
    else:
        morsel["max-age"] = 300
    return morsel.OutputString()


def schedule_confirmation_cookie_name(schedule_draft_id: str) -> str:
    return f"ready_schedule_confirm_{schedule_draft_id}"


def schedule_confirmation_cookie(
    schedule_draft_id: str, token: str, *, clear: bool = False
) -> str:
    cookie = SimpleCookie()
    name = schedule_confirmation_cookie_name(schedule_draft_id)
    cookie[name] = "" if clear else token
    morsel = cookie[name]
    morsel["path"] = f"/api/schedule-drafts/{schedule_draft_id}/confirm"
    morsel["httponly"] = True
    morsel["samesite"] = "Strict"
    if clear:
        morsel["max-age"] = 0
    else:
        morsel["max-age"] = 300
    return morsel.OutputString()


class ReadyHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], app: DemoApp, web_root: Path) -> None:
        bind_ip = _loopback_ip(address[0])
        if bind_ip is None:
            raise ValueError("ReadyHTTPServer requires a literal loopback bind address")
        self.address_family = (
            socket.AF_INET6 if bind_ip.version == 6 else socket.AF_INET
        )
        super().__init__(address, ReadyRequestHandler)
        self.app = app
        self.web_root = web_root.resolve()

    def server_bind(self) -> None:
        if self.address_family == socket.AF_INET6:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()

    def verify_request(self, request: object, client_address: object) -> bool:
        return is_loopback_peer_address(client_address) and super().verify_request(
            request, client_address
        )


class ReadyRequestHandler(BaseHTTPRequestHandler):
    server: ReadyHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        # Do not write message bodies, session IDs, cookies, or tokens to logs.
        return

    def _enforce_local_browser_boundary(self, *, check_origin: bool) -> None:
        if not is_loopback_peer_address(self.client_address):
            raise WalletError(
                "LOCAL_PEER_REQUIRED",
                "This local mock demo only accepts loopback connections.",
                403,
            )
        if not is_local_host_authority(self.headers.get("Host")):
            raise WalletError(
                "LOCAL_HOST_REQUIRED",
                "This local mock demo only accepts localhost or loopback Host values.",
                403,
            )
        origin = self.headers.get("Origin")
        if check_origin and origin and not is_local_origin(origin):
            raise WalletError(
                "LOCAL_ORIGIN_REQUIRED",
                "This local mock demo only accepts localhost or loopback browser origins.",
                403,
            )

    def do_OPTIONS(self) -> None:
        try:
            self._enforce_local_browser_boundary(check_origin=False)
        except WalletError as error:
            self._error(error.status, error.code, error.message)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, X-Demo-Session, X-CSRF-Token"
        )
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            self._enforce_local_browser_boundary(check_origin=False)
            if parsed.path == "/api/bootstrap":
                query = parse_qs(parsed.query, keep_blank_values=True)
                if set(query) != {"user_id"} or len(query["user_id"]) != 1:
                    raise WalletError(
                        "INVALID_BOOTSTRAP", "Choose exactly one demo user_id."
                    )
                self._json(
                    HTTPStatus.OK, self.server.app.bootstrap(query["user_id"][0])
                )
                return
            if parsed.path.startswith("/api/"):
                session = self._session(require_csrf=False)
                schedule_draft_match = _SCHEDULE_DRAFT_STATUS_RE.fullmatch(parsed.path)
                if schedule_draft_match:
                    self._json(
                        HTTPStatus.OK,
                        self.server.app.schedule_draft_status(
                            session, schedule_draft_match.group(1)
                        ),
                    )
                    return
                draft_match = _DRAFT_STATUS_RE.fullmatch(parsed.path)
                if draft_match:
                    self._json(
                        HTTPStatus.OK,
                        self.server.app.draft_status(session, draft_match.group(1)),
                    )
                    return
                transaction_match = _TRANSACTION_STATUS_RE.fullmatch(parsed.path)
                if transaction_match:
                    self.server.app._require_customer(session)
                    transaction = self.server.app.wallet.get_transaction_status(
                        session["user_id"], transaction_match.group(1)
                    )
                    self._json(HTTPStatus.OK, {"transaction": transaction})
                    return
                self._error(
                    HTTPStatus.NOT_FOUND,
                    "ROUTE_NOT_FOUND",
                    "The requested API route was not found.",
                )
                return
            self._static(parsed.path)
        except WalletError as error:
            self._error(error.status, error.code, error.message)
        except Exception:  # noqa: BLE001 - HTTP boundary intentionally returns a redacted error
            self._error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "The local demo could not complete that request.",
            )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            # CLI tests have no Origin; a browser-supplied Origin must be local.
            self._enforce_local_browser_boundary(check_origin=True)
            if not parsed.path.startswith("/api/"):
                self._error(
                    HTTPStatus.NOT_FOUND,
                    "ROUTE_NOT_FOUND",
                    "The requested route was not found.",
                )
                return
            session = self._session(require_csrf=True)
            body = self._read_json()
            if parsed.path == "/api/chat":
                self._strict_keys(body, {"message"})
                response, issued = self.server.app.chat(session, body["message"])
                headers = self._issue_headers(issued)
                self._json(HTTPStatus.OK, response, headers)
                return
            action_match = _ACTION_RE.fullmatch(parsed.path)
            if action_match:
                response, issued = self.server.app.dispatch_action(
                    session, action_match.group(1), body
                )
                headers = self._issue_headers(issued)
                self._json(HTTPStatus.OK, response, headers)
                return
            schedule_confirm_match = _SCHEDULE_DRAFT_CONFIRM_RE.fullmatch(parsed.path)
            if schedule_confirm_match:
                self._strict_keys(body, set())
                schedule_draft_id = schedule_confirm_match.group(1)
                token = self._schedule_confirmation_token(schedule_draft_id)
                response = self.server.app.confirm_schedule_draft(
                    session, schedule_draft_id, token
                )
                self._json(
                    HTTPStatus.OK,
                    response,
                    {
                        "Set-Cookie": schedule_confirmation_cookie(
                            schedule_draft_id, "", clear=True
                        )
                    },
                )
                return
            schedule_cancel_match = _SCHEDULE_DRAFT_CANCEL_RE.fullmatch(parsed.path)
            if schedule_cancel_match:
                self._strict_keys(body, set())
                schedule_draft_id = schedule_cancel_match.group(1)
                response = self.server.app.cancel_schedule_draft(
                    session, schedule_draft_id
                )
                self._json(
                    HTTPStatus.OK,
                    response,
                    {
                        "Set-Cookie": schedule_confirmation_cookie(
                            schedule_draft_id, "", clear=True
                        )
                    },
                )
                return
            confirm_match = _DRAFT_CONFIRM_RE.fullmatch(parsed.path)
            if confirm_match:
                self._strict_keys(body, set())
                draft_id = confirm_match.group(1)
                token = self._confirmation_token(draft_id)
                response = self.server.app.confirm_draft(session, draft_id, token)
                self._json(
                    HTTPStatus.OK,
                    response,
                    {"Set-Cookie": confirmation_cookie(draft_id, "", clear=True)},
                )
                return
            cancel_match = _DRAFT_CANCEL_RE.fullmatch(parsed.path)
            if cancel_match:
                self._strict_keys(body, set())
                draft_id = cancel_match.group(1)
                response = self.server.app.cancel_draft(session, draft_id)
                self._json(
                    HTTPStatus.OK,
                    response,
                    {"Set-Cookie": confirmation_cookie(draft_id, "", clear=True)},
                )
                return
            self._error(
                HTTPStatus.NOT_FOUND,
                "ROUTE_NOT_FOUND",
                "The requested API route was not found.",
            )
        except WalletError as error:
            self._error(error.status, error.code, error.message)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._error(
                HTTPStatus.BAD_REQUEST, "INVALID_JSON", "Body must be valid UTF-8 JSON."
            )
        except Exception:  # noqa: BLE001 - HTTP boundary intentionally returns a redacted error
            self._error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "The local demo could not complete that request.",
            )

    def _session(self, *, require_csrf: bool) -> dict[str, str]:
        return self.server.app.wallet.require_session(
            self.headers.get("X-Demo-Session"),
            self.headers.get("X-CSRF-Token"),
            require_csrf=require_csrf,
        )

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError as error:
            raise WalletError(
                "INVALID_REQUEST", "Content-Length is invalid."
            ) from error
        if length < 0 or length > MAX_BODY_BYTES:
            raise WalletError("REQUEST_TOO_LARGE", "Request body is too large.", 413)
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise WalletError("INVALID_REQUEST", "JSON body must be an object.")
        return payload

    @staticmethod
    def _strict_keys(body: dict[str, Any], expected: set[str]) -> None:
        if set(body) != expected:
            raise WalletError(
                "INVALID_REQUEST", "Request fields are not allowed for this route."
            )

    def _confirmation_token(self, draft_id: str) -> str | None:
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
        except (ValueError, KeyError):
            return None
        morsel = cookies.get(confirmation_cookie_name(draft_id))
        return morsel.value if morsel else None

    def _schedule_confirmation_token(self, schedule_draft_id: str) -> str | None:
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
        except (ValueError, KeyError):
            return None
        morsel = cookies.get(schedule_confirmation_cookie_name(schedule_draft_id))
        return morsel.value if morsel else None

    @staticmethod
    def _issue_headers(
        issued: IssuedDraft | IssuedScheduleDraft | None,
    ) -> dict[str, str] | None:
        if issued is None:
            return None
        if isinstance(issued, IssuedScheduleDraft):
            return {
                "Set-Cookie": schedule_confirmation_cookie(
                    issued.schedule_draft["id"], issued.confirmation_token
                )
            }
        return {
            "Set-Cookie": confirmation_cookie(
                issued.draft["id"], issued.confirmation_token
            )
        }

    def _json(
        self,
        status: HTTPStatus | int,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(encoded)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, status: HTTPStatus | int, code: str, message: str) -> None:
        self._json(status, {"error": {"code": code, "message": message}})

    def _static(self, request_path: str) -> None:
        relative = (
            "index.html"
            if request_path in ("", "/")
            else unquote(request_path).lstrip("/")
        )
        candidate = (self.server.web_root / relative).resolve()
        try:
            candidate.relative_to(self.server.web_root)
        except ValueError:
            self._error(
                HTTPStatus.NOT_FOUND, "NOT_FOUND", "The requested file was not found."
            )
            return
        if not candidate.is_file():
            self._error(
                HTTPStatus.NOT_FOUND, "NOT_FOUND", "The requested file was not found."
            )
            return
        content = candidate.read_bytes()
        content_type = (
            mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        )
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            f"{content_type}; charset=utf-8"
            if content_type.startswith("text/")
            else content_type,
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def create_server(
    database_path: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    web_root: str | Path | None = None,
) -> ReadyHTTPServer:
    bind_host = resolve_loopback_bind_host(host)
    project_root = Path(__file__).resolve().parent
    database = (
        Path(database_path)
        if database_path is not None
        else project_root / "data" / "demo_wallet.sqlite3"
    )
    root = Path(web_root) if web_root is not None else project_root / "web"
    return ReadyHTTPServer((bind_host, port), DemoApp(database), root)


def main() -> None:
    database_path = os.environ.get("READY_DB_PATH")
    server = create_server(database_path)
    host, port = server.server_address[:2]
    display_host = f"[{host}]" if ":" in host else host
    print(f"READY mock wallet is running locally at http://{display_host}:{port}")
    print("Synthetic fixtures only. No external model or payment service is enabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
