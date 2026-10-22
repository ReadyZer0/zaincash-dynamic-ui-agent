"""Reject a common endpoint setup mistake before a credential is transmitted."""

import unittest

from llm_agent import LLMConfig


class ProviderSetupTests(unittest.TestCase):
    def test_completion_url_is_not_a_base_url(self):
        for suffix in ("/chat/completions", "/chat/completions/"):
            config = LLMConfig(mode="llm", base_url="https://provider.example/v1" + suffix,
                               model="test-model", api_key="test-only-key")
            self.assertIn("without /chat/completions", config.configuration_error())
        self.assertIsNone(LLMConfig(mode="llm", base_url="http://127.0.0.1:8000/v1", model="test-model").configuration_error())
