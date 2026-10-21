"""HTTP regressions for the mock-only monthly reminder schedule slice."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from pathlib import Path

from core import MockWallet
from server import create_server


class ApiClient:
    def __init__(self, port: int) -> None:
        self.port = port
        self.session_id: str | None = None
        self.csrf_token: str | None = None
        self.cookies: dict[str, str] = {}

    def bootstrap(self, user_id: str) -> dict:
        status, payload, _headers = self.request(
            "GET", f"/api/bootstrap?user_id={user_id}"
        )
        assert status == 200, payload
        self.session_id = payload["session"]["id"]
        self.csrf_token = payload["session"]["csrf_token"]
        return payload

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        authenticated: bool = True,
        csrf: bool = True,
        cookie_override: dict[str, str] | None = None,
    ) -> tuple[int, dict, dict[str, str]]:
        body = b""
        headers: dict[str, str] = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
            headers["Content-Length"] = str(len(body))
        if authenticated and self.session_id:
            headers["X-Demo-Session"] = self.session_id
        if csrf and self.csrf_token:
            headers["X-CSRF-Token"] = self.csrf_token
        cookie_values = self.cookies if cookie_override is None else cookie_override
        if cookie_values:
            headers["Cookie"] = "; ".join(
                f"{key}={value}" for key, value in cookie_values.items()
            )
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            response_headers = {
                key.lower(): value for key, value in response.getheaders()
            }
        finally:
            connection.close()
        set_cookie = response_headers.get("set-cookie")
        if set_cookie:
            parsed = SimpleCookie(set_cookie)
            for name, morsel in parsed.items():
                if morsel["max-age"] == "0":
                    self.cookies.pop(name, None)
                else:
                    self.cookies[name] = morsel.value
        return response.status, json.loads(raw.decode("utf-8")), response_headers

    def schedule_confirmation_cookie_for(
        self, schedule_draft_id: str
    ) -> dict[str, str]:
        name = f"ready_schedule_confirm_{schedule_draft_id}"
        return {name: self.cookies[name]}


class M2ScheduleApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tempdir.name) / "m2-schedules.sqlite3"
        self.server = create_server(
            self.database_path,
            port=0,
            web_root=Path(self.tempdir.name) / "missing-web",
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = int(self.server.server_address[1])

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.tempdir.cleanup()

    @staticmethod
    def future_time(days: int = 2) -> str:
        value = datetime.now(timezone.utc) + timedelta(days=days)
        return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def customer(self, user_id: str = "demo_amina") -> tuple[ApiClient, dict]:
        client = ApiClient(self.port)
        return client, client.bootstrap(user_id)

    def balance(self, client: ApiClient) -> int:
        status, payload, _ = client.request("POST", "/api/actions/VIEW_BALANCE", {})
        self.assertEqual(status, 200, payload)
        return payload["view"]["data"]["available_minor"]

    def history_count(self, client: ApiClient) -> int:
        status, payload, _ = client.request("POST", "/api/actions/VIEW_HISTORY", {})
        self.assertEqual(status, 200, payload)
        return len(payload["view"]["data"]["items"])

    def prepare_schedule(
        self,
        client: ApiClient,
        *,
        scheduled_for: str | None = None,
        recurrence: str = "MONTHLY",
    ) -> tuple[str, dict]:
        status, payload, _ = client.request(
            "POST",
            "/api/actions/OPEN_SCHEDULED_TRANSFER",
            {
                "recipient_id": "contact_ali_diaa",
                "amount_minor": 50_000,
                "currency": "IQD",
                "scheduled_for": scheduled_for or self.future_time(),
                "timezone": "Asia/Baghdad",
                "recurrence": recurrence,
            },
        )
        self.assertEqual(status, 200, payload)
        return payload["schedule_draft"]["id"], payload

    def test_registry_bootstrap_and_chat_expose_owner_scoped_schedule_form(
        self,
    ) -> None:
        client, bootstrap = self.customer()
        before = self.balance(client)
        action = next(
            item
            for item in bootstrap["actions"]
            if item["id"] == "OPEN_SCHEDULED_TRANSFER"
        )
        self.assertTrue(action["requires_confirmation"])
        self.assertEqual(action["component"], "scheduled-transfer-review")
        self.assertEqual(
            action["parameters"],
            [
                "recipient_id",
                "amount_minor",
                "currency",
                "scheduled_for",
                "timezone",
                "recurrence",
            ],
        )
        form = bootstrap["schedule_transfer_form"]
        self.assertEqual(form["kind"], "scheduled_transfer_form")
        self.assertEqual(form["data"]["recurrence"], "MONTHLY")
        self.assertEqual(form["data"]["timezone"], "Asia/Baghdad")
        self.assertEqual(form["data"]["authorization_mode"], "REMIND_AND_PREPARE")
        self.assertEqual(form["data"]["execution_mode"], "FRESH_PAYMENT_DRAFT_REQUIRED")
        self.assertEqual(
            form["data"]["allowed_day_of_month"], {"minimum": 1, "maximum": 28}
        )
        recipient_ids = {item["id"] for item in form["data"]["recipients"]}
        self.assertEqual(recipient_ids, {"contact_ali_diaa", "contact_ali_mohammed"})

        status, chat, _ = client.request(
            "POST", "/api/chat", {"message": "أريد جدولة تحويل شهري"}
        )
        self.assertEqual(status, 200, chat)
        self.assertEqual(chat["actions"][0]["id"], "OPEN_SCHEDULED_TRANSFER")
        self.assertEqual(chat["view"]["kind"], "scheduled_transfer_form")
        self.assertEqual(
            {item["id"] for item in chat["view"]["data"]["recipients"]},
            recipient_ids,
        )
        self.assertNotIn("schedule_draft", chat)
        self.assertNotIn("confirmation_token", json.dumps(chat, ensure_ascii=False))
        self.assertEqual(before, self.balance(client))

    def test_schedule_review_validates_future_monthly_details(self) -> None:
        client, _ = self.customer()
        before = self.balance(client)
        schedule_draft_id, prepared = self.prepare_schedule(client)
        draft = prepared["schedule_draft"]
        self.assertTrue(schedule_draft_id.startswith("schedule_draft_"))
        self.assertEqual(draft["kind"], "scheduled_transfer")
        self.assertEqual(draft["state"], "AWAITING_CONFIRMATION")
        self.assertTrue(draft["can_confirm"])
        for key in (
            "recipient_or_biller",
            "amount_minor",
            "fee_minor",
            "total_debit_minor",
            "scheduled_for",
            "timezone",
            "recurrence",
            "authorization_mode",
            "execution_mode",
            "confirmation_expires_at",
            "warnings",
        ):
            self.assertIn(key, draft["review"])
        self.assertEqual(draft["review"]["recurrence"], "MONTHLY")
        self.assertEqual(draft["review"]["authorization_mode"], "REMIND_AND_PREPARE")
        self.assertEqual(
            draft["review"]["execution_mode"], "FRESH_PAYMENT_DRAFT_REQUIRED"
        )
        self.assertEqual(before, self.balance(client))

        status, too_soon, _ = client.request(
            "POST",
            "/api/actions/OPEN_SCHEDULED_TRANSFER",
            {
                "recipient_id": "contact_ali_diaa",
                "amount_minor": 50_000,
                "currency": "IQD",
                "scheduled_for": self.future_time(0),
                "timezone": "Asia/Baghdad",
                "recurrence": "MONTHLY",
            },
        )
        self.assertEqual(status, 409, too_soon)
        self.assertEqual(too_soon["error"]["code"], "SCHEDULE_TIME_NOT_FUTURE")
        status, unsupported, _ = client.request(
            "POST",
            "/api/actions/OPEN_SCHEDULED_TRANSFER",
            {
                "recipient_id": "contact_ali_diaa",
                "amount_minor": 50_000,
                "currency": "IQD",
                "scheduled_for": self.future_time(),
                "timezone": "Asia/Baghdad",
                "recurrence": "WEEKLY",
            },
        )
        self.assertEqual(status, 400, unsupported)
        self.assertEqual(unsupported["error"]["code"], "UNSUPPORTED_RECURRENCE")
        status, month_end, _ = client.request(
            "POST",
            "/api/actions/OPEN_SCHEDULED_TRANSFER",
            {
                "recipient_id": "contact_ali_diaa",
                "amount_minor": 50_000,
                "currency": "IQD",
                "scheduled_for": "2030-01-29T12:00:00Z",
                "timezone": "Asia/Baghdad",
                "recurrence": "MONTHLY",
            },
        )
        self.assertEqual(status, 400, month_end)
        self.assertEqual(month_end["error"]["code"], "UNSUPPORTED_MONTHLY_DAY")
        self.assertEqual(before, self.balance(client))

    def test_schedule_confirm_is_idempotent_configuration_without_debit(self) -> None:
        client, _ = self.customer()
        before_balance = self.balance(client)
        before_history = self.history_count(client)
        schedule_draft_id, _ = self.prepare_schedule(client)
        confirmation_cookie = client.schedule_confirmation_cookie_for(schedule_draft_id)
        status, confirmed, _ = client.request(
            "POST", f"/api/schedule-drafts/{schedule_draft_id}/confirm", {}
        )
        self.assertEqual(status, 200, confirmed)
        self.assertNotIn("transaction", confirmed)
        self.assertEqual(confirmed["schedule_draft"]["state"], "SCHEDULED_MOCK_ONLY")
        schedule = confirmed["schedule"]
        self.assertEqual(schedule["status"], "ACTIVE_MOCK_ONLY")
        self.assertEqual(schedule["debit_minor"], 0)
        self.assertTrue(schedule["requires_fresh_payment_draft"])
        self.assertEqual(schedule["execution_mode"], "FRESH_PAYMENT_DRAFT_REQUIRED")
        self.assertEqual(before_balance, self.balance(client))
        self.assertEqual(before_history, self.history_count(client))

        status, wrong_path, _ = client.request(
            "POST", f"/api/drafts/{schedule_draft_id}/confirm", {}
        )
        self.assertEqual(status, 404, wrong_path)
        self.assertEqual(wrong_path["error"]["code"], "ROUTE_NOT_FOUND")
        status, retried, _ = client.request(
            "POST",
            f"/api/schedule-drafts/{schedule_draft_id}/confirm",
            {},
            cookie_override=confirmation_cookie,
        )
        self.assertEqual(status, 200, retried)
        self.assertTrue(retried["schedule"]["duplicate"])
        self.assertEqual(retried["schedule"]["id"], schedule["id"])
        self.assertEqual(before_balance, self.balance(client))

        status, recovered, _ = client.request(
            "GET", f"/api/schedule-drafts/{schedule_draft_id}/status"
        )
        self.assertEqual(status, 200, recovered)
        self.assertEqual(recovered["schedule"]["id"], schedule["id"])
        self.assertNotIn("transaction", recovered)
        reopened = MockWallet(self.database_path)
        after_restart = reopened.get_schedule_draft_status(
            "demo_amina", schedule_draft_id
        )
        self.assertEqual(after_restart["schedule"]["id"], schedule["id"])
        self.assertEqual(before_balance, self.balance(client))

    def test_schedule_confirmation_requires_current_owner_session_cookie_and_expiry(
        self,
    ) -> None:
        amina, _ = self.customer()
        hassan, _ = self.customer("demo_hassan")
        before = self.balance(amina)
        schedule_draft_id, _ = self.prepare_schedule(amina)
        schedule_cookie = amina.schedule_confirmation_cookie_for(schedule_draft_id)
        status, denied, _ = amina.request(
            "POST",
            f"/api/schedule-drafts/{schedule_draft_id}/confirm",
            {},
            cookie_override={},
        )
        self.assertEqual(status, 403, denied)
        self.assertEqual(denied["error"]["code"], "FORBIDDEN")
        status, cross_owner, _ = hassan.request(
            "GET", f"/api/schedule-drafts/{schedule_draft_id}/status"
        )
        self.assertEqual(status, 404, cross_owner)
        self.assertEqual(cross_owner["error"]["code"], "SCHEDULE_DRAFT_NOT_FOUND")

        status, transfer, _ = amina.request(
            "POST",
            "/api/actions/OPEN_TRANSFER",
            {
                "recipient_id": "contact_ali_diaa",
                "amount_minor": 50_000,
                "currency": "IQD",
            },
        )
        self.assertEqual(status, 200, transfer)
        status, preserved_schedule, _ = amina.request(
            "POST",
            f"/api/schedule-drafts/{schedule_draft_id}/confirm",
            {},
            cookie_override=schedule_cookie,
        )
        self.assertEqual(status, 200, preserved_schedule)
        self.assertEqual(before, self.balance(amina))

        stale_id, _ = self.prepare_schedule(amina)
        stale_cookie = amina.schedule_confirmation_cookie_for(stale_id)
        _current_id, _ = self.prepare_schedule(amina)
        status, stale, _ = amina.request(
            "POST",
            f"/api/schedule-drafts/{stale_id}/confirm",
            {},
            cookie_override=stale_cookie,
        )
        self.assertEqual(status, 409, stale)
        self.assertEqual(stale["error"]["code"], "STALE_SCHEDULE_CONFIRMATION")

        cancelled_id, _ = self.prepare_schedule(amina)
        cancelled_cookie = amina.schedule_confirmation_cookie_for(cancelled_id)
        status, cancelled, _ = amina.request(
            "POST", f"/api/schedule-drafts/{cancelled_id}/cancel", {}
        )
        self.assertEqual(status, 200, cancelled)
        self.assertEqual(cancelled["schedule_draft"]["state"], "CANCELLED")
        status, cancelled_confirm, _ = amina.request(
            "POST",
            f"/api/schedule-drafts/{cancelled_id}/confirm",
            {},
            cookie_override=cancelled_cookie,
        )
        self.assertEqual(status, 409, cancelled_confirm)
        self.assertEqual(cancelled_confirm["error"]["code"], "SCHEDULE_DRAFT_CANCELLED")

        expired_id, _ = self.prepare_schedule(amina)
        expired_cookie = amina.schedule_confirmation_cookie_for(expired_id)
        self.server.app.wallet._expire_schedule_draft_for_test(expired_id)
        status, expired, _ = amina.request(
            "POST",
            f"/api/schedule-drafts/{expired_id}/confirm",
            {},
            cookie_override=expired_cookie,
        )
        self.assertEqual(status, 409, expired)
        self.assertEqual(expired["error"]["code"], "SCHEDULE_DRAFT_EXPIRED")
        self.assertEqual(before, self.balance(amina))

    def test_schedule_and_payment_reviews_keep_separate_active_pointers(self) -> None:
        client, _ = self.customer()
        before = self.balance(client)
        status, payment, _ = client.request(
            "POST",
            "/api/actions/OPEN_TRANSFER",
            {
                "recipient_id": "contact_ali_diaa",
                "amount_minor": 50_000,
                "currency": "IQD",
            },
        )
        self.assertEqual(status, 200, payment)
        payment_draft_id = payment["draft"]["id"]
        payment_cookie = {
            f"ready_confirm_{payment_draft_id}": client.cookies[
                f"ready_confirm_{payment_draft_id}"
            ]
        }
        schedule_draft_id, _ = self.prepare_schedule(client)
        schedule_cookie = client.schedule_confirmation_cookie_for(schedule_draft_id)
        conversation = self.server.app.wallet.get_conversation(client.session_id)
        self.assertEqual(conversation["active_draft_id"], payment_draft_id)
        self.assertEqual(conversation["active_schedule_draft_id"], schedule_draft_id)

        status, payment_confirmed, _ = client.request(
            "POST",
            f"/api/drafts/{payment_draft_id}/confirm",
            {},
            cookie_override=payment_cookie,
        )
        self.assertEqual(status, 200, payment_confirmed)
        after_payment = before - payment_confirmed["transaction"]["debit_minor"]
        self.assertEqual(after_payment, self.balance(client))
        conversation = self.server.app.wallet.get_conversation(client.session_id)
        self.assertNotIn("active_draft_id", conversation)
        self.assertEqual(conversation["active_schedule_draft_id"], schedule_draft_id)

        status, schedule_confirmed, _ = client.request(
            "POST",
            f"/api/schedule-drafts/{schedule_draft_id}/confirm",
            {},
            cookie_override=schedule_cookie,
        )
        self.assertEqual(status, 200, schedule_confirmed)
        self.assertEqual(after_payment, self.balance(client))
        self.assertEqual(self.server.app.wallet.get_conversation(client.session_id), {})

    def test_concurrent_schedule_confirmation_converges_without_debit(self) -> None:
        client, _ = self.customer()
        before = self.balance(client)
        schedule_draft_id, _ = self.prepare_schedule(client)
        confirmation_cookie = client.schedule_confirmation_cookie_for(schedule_draft_id)
        barrier = threading.Barrier(2)

        def confirm_once() -> tuple[int, dict]:
            other = ApiClient(self.port)
            other.session_id = client.session_id
            other.csrf_token = client.csrf_token
            barrier.wait(timeout=3)
            status, payload, _ = other.request(
                "POST",
                f"/api/schedule-drafts/{schedule_draft_id}/confirm",
                {},
                cookie_override=confirmation_cookie,
            )
            return status, payload

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: confirm_once(), range(2)))
        self.assertEqual([status for status, _ in results], [200, 200])
        schedule_ids = {payload["schedule"]["id"] for _, payload in results}
        self.assertEqual(len(schedule_ids), 1)
        self.assertEqual(
            sorted(payload["schedule"]["duplicate"] for _, payload in results),
            [False, True],
        )
        self.assertEqual(before, self.balance(client))


if __name__ == "__main__":
    unittest.main(verbosity=2)
