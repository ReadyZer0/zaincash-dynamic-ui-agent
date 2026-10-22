"""Reject a common endpoint setup mistake before a credential is transmitted."""

import io
import json
import unittest

from llm_agent import GEMINI_BASE_URL, GEMINI_FLASH_MODEL, LLMConfig, OpenAICompatibleClient, tool_definitions


class ProviderSetupTests(unittest.TestCase):
    def test_gemini_request_uses_documented_endpoint_and_low_reasoning(self):
        class NoNetworkOpener:
            request = None

            def open(self, request, *, timeout):
                self.request = request
                answer = {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "fixture"}}]}
                return io.BytesIO(json.dumps(answer).encode("utf-8"))

        config = LLMConfig(mode="llm", base_url=GEMINI_BASE_URL,
                           model=GEMINI_FLASH_MODEL, api_key="test-only-key", request_cap=1)
        client = OpenAICompatibleClient(config)
        opener = NoNetworkOpener()
        client._opener = opener
        definitions = tool_definitions()
        self.assertEqual(client.complete([{"role": "user", "content": "synthetic"}], definitions, 2)["content"], "fixture")
        self.assertEqual(opener.request.full_url, GEMINI_BASE_URL + "/chat/completions")
        payload = json.loads(opener.request.data)
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertNotIn("parallel_tool_calls", payload)
        self.assertNotIn("parameters", next(item for item in payload["tools"] if item["function"]["name"] == "VIEW_BALANCE")["function"])
        transfer = next(item for item in payload["tools"] if item["function"]["name"] == "OPEN_TRANSFER")
        self.assertNotIn("additionalProperties", transfer["function"]["parameters"])
        self.assertEqual(transfer["function"]["parameters"]["required"], ["recipient_id", "amount_minor", "currency"])
        self.assertIn("additionalProperties", next(item for item in definitions if item["function"]["name"] == "OPEN_TRANSFER")["function"]["parameters"])
        self.assertNotIn("test-only-key", opener.request.data.decode("utf-8"))

    def test_request_cap_must_be_valid(self):
        base = {"READY_AGENT_MODE": "llm", "READY_LLM_BASE_URL": GEMINI_BASE_URL,
                "READY_LLM_MODEL": GEMINI_FLASH_MODEL, "READY_LLM_API_KEY": "test-only-key"}
        self.assertEqual(LLMConfig.from_env({**base, "READY_LLM_REQUEST_CAP": "5"}).request_cap, 5)
        for value in ("0", "101", "many"):
            self.assertIn("READY_LLM_REQUEST_CAP", LLMConfig.from_env({**base, "READY_LLM_REQUEST_CAP": value}).configuration_error())

    def test_completion_url_is_not_a_base_url(self):
        for suffix in ("/chat/completions", "/chat/completions/"):
            config = LLMConfig(mode="llm", base_url="https://provider.example/v1" + suffix,
                               model="test-model", api_key="test-only-key")
            self.assertIn("without /chat/completions", config.configuration_error())
        self.assertIsNone(LLMConfig(mode="llm", base_url="http://127.0.0.1:8000/v1", model="test-model").configuration_error())
