"""Exercise the APK's same-origin HTTP path with a local fake model API.

The APK is a WebView client of this backend, not a holder of provider secrets.
These tests use synthetic data and never contact Gemini or another cloud API.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from llm_agent import LLMConfig
from server import create_server


ROOT = Path(__file__).resolve().parents[1]


class AndroidApiPathTests(unittest.TestCase):
    def test_webview_backend_to_model_tool_and_safe_failure(self) -> None:
        recorded: list[dict] = []
        fixture_key = "synthetic-local-fixture-key"

        class FakeProvider(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                recorded.append({
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "body": body,
                })
                if len(recorded) == 3:
                    self.send_response(429)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if len(recorded) == 1:
                    message = {
                        "role": "assistant", "content": None,
                        "tool_calls": [{
                            "id": "balance_fixture_call", "type": "function",
                            "function": {"name": "VIEW_BALANCE", "arguments": "{}"},
                        }],
                    }
                else:
                    message = {"role": "assistant", "content": "رصيدك ظاهر بالبطاقة."}
                response = json.dumps({"choices": [{"finish_reason": "stop", "message": message}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, _format: str, *_args: object) -> None:
                pass

        def request(port: int, method: str, path: str, body: dict | None = None,
                    session: dict | None = None) -> tuple[int, bytes]:
            headers = {"Accept": "application/json"}
            payload = b"" if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
            if body is not None:
                headers["Content-Type"] = "application/json"
            if session:
                headers["X-Demo-Session"] = session["id"]
                headers["X-CSRF-Token"] = session["csrf_token"]
                headers["Origin"] = f"http://127.0.0.1:{port}"
            connection = HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                connection.request(method, path, body=payload, headers=headers)
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()

        provider = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
        provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
        provider_thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                config = LLMConfig(
                    mode="llm", base_url=f"http://127.0.0.1:{provider.server_port}/v1",
                    model="synthetic-fixture", api_key=fixture_key, request_cap=3,
                )
                app = create_server(Path(directory) / "wallet.sqlite3", port=0,
                                    web_root=ROOT / "web", agent_config=config)
                app_thread = threading.Thread(target=app.serve_forever, daemon=True)
                app_thread.start()
                try:
                    port = app.server_address[1]
                    status, page = request(port, "GET", "/")
                    self.assertEqual(status, 200)
                    self.assertIn(b"/app.js", page)
                    status, bootstrap_raw = request(port, "GET", "/api/bootstrap?user_id=demo_amina")
                    self.assertEqual(status, 200)
                    bootstrap = json.loads(bootstrap_raw)
                    self.assertEqual(bootstrap["agent"]["mode"], "LIVE_MODEL")
                    self.assertTrue(bootstrap["agent"]["configured"])
                    session = bootstrap["session"]

                    status, chat_raw = request(port, "POST", "/api/chat",
                                               {"message": "شكد رصيدي هسه؟"}, session)
                    self.assertEqual(status, 200, chat_raw)
                    chat = json.loads(chat_raw)
                    self.assertEqual(chat["agent"]["last_request"], "succeeded")
                    self.assertEqual(chat["view"]["kind"], "balance")
                    self.assertEqual(chat["view"]["data"]["available_minor"], 150_000)
                    self.assertNotIn("draft", chat)
                    self.assertNotIn(fixture_key, bootstrap_raw.decode() + chat_raw.decode())
                    self.assertEqual(config.provider_request_attempts(), 2)

                    status, failed_raw = request(port, "POST", "/api/chat",
                                                 {"message": "شكد رصيدي هسه؟"}, session)
                    self.assertEqual(status, 503)
                    self.assertEqual(json.loads(failed_raw)["error"]["code"], "MODEL_RATE_LIMIT")
                    self.assertEqual(config.provider_request_attempts(), 3)
                    self.assertEqual(app.app.wallet.get_balance("demo_amina")["available_minor"], 150_000)
                    self.assertEqual(len(recorded), 3)
                    self.assertTrue(all(item["path"] == "/v1/chat/completions" for item in recorded))
                    self.assertTrue(all(item["authorization"] == f"Bearer {fixture_key}" for item in recorded))
                    self.assertNotIn(session["id"], json.dumps(recorded))
                    self.assertNotIn(session["csrf_token"], json.dumps(recorded))
                finally:
                    app.shutdown()
                    app.server_close()
                    app_thread.join(timeout=3)
        finally:
            provider.shutdown()
            provider.server_close()
            provider_thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
