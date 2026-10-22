"""Launch preparation must never leak keys or silently enable paid calls."""

from __future__ import annotations

import getpass
import io
import os
import unittest
import warnings
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts.ready import hidden_key, main, runtime_environment
from llm_agent import GEMINI_BASE_URL, GEMINI_FLASH_MODEL


class LauncherTests(unittest.TestCase):
    def test_gemini_preset_uses_five_request_cap_and_fresh_hidden_key(self):
        inherited = {"READY_LLM_API_KEY": "old-exposed-key", "READY_LLM_BASE_URL": "https://old.example/v1",
                     "READY_LLM_ENABLE_THINKING": "true"}
        with patch.dict(os.environ, inherited, clear=True), patch("scripts.ready.hidden_key", return_value="new-test-only-key"), patch("scripts.ready.backend_credentials.read_key", return_value=None):
            with runtime_environment("llm", True, "gemini"):
                self.assertEqual(os.environ["READY_LLM_BASE_URL"], GEMINI_BASE_URL)
                self.assertEqual(os.environ["READY_LLM_MODEL"], GEMINI_FLASH_MODEL)
                self.assertEqual(os.environ["READY_LLM_REQUEST_CAP"], "5")
                self.assertEqual(os.environ["READY_LLM_API_KEY"], "new-test-only-key")
                self.assertNotIn("READY_LLM_ENABLE_THINKING", os.environ)
            self.assertEqual(os.environ["READY_LLM_API_KEY"], "old-exposed-key")
            self.assertEqual(os.environ["READY_LLM_BASE_URL"], "https://old.example/v1")
            self.assertEqual(os.environ["READY_LLM_ENABLE_THINKING"], "true")
            self.assertNotIn("READY_LLM_REQUEST_CAP", os.environ)

    def test_gemini_preset_requires_explicit_mode_and_network_opt_in(self):
        with patch("scripts.ready.hidden_key", side_effect=AssertionError("Do not prompt")):
            with self.assertRaisesRegex(ValueError, "--mode llm"):
                with runtime_environment("offline", False, "gemini"):
                    self.fail("Preset accepted offline mode")
            with self.assertRaisesRegex(ValueError, "allow-network"):
                with runtime_environment("llm", False, "gemini"):
                    self.fail("Preset accepted network without opt-in")

    def test_saved_gemini_key_requires_live_opt_in_and_never_prompts(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("scripts.ready.backend_credentials.read_key", return_value="stored-test-only-key") as read,
            patch("scripts.ready.hidden_key", side_effect=AssertionError("Must use stored key")),
        ):
            with self.assertRaisesRegex(ValueError, "allow-network"):
                with runtime_environment("llm", False, "gemini"):
                    self.fail("Started without opt-in")
            read.assert_not_called()
            with runtime_environment("llm", True, "gemini"):
                self.assertEqual(os.environ["READY_LLM_API_KEY"], "stored-test-only-key")
            self.assertNotIn("READY_LLM_API_KEY", os.environ)
            read.assert_called_once_with()

    def test_invalid_saved_key_is_rejected_without_environment_storage(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("scripts.ready.backend_credentials.read_key", return_value="fixture\u200bkey"),
            patch("scripts.ready.hidden_key", side_effect=AssertionError("Do not prompt")),
            self.assertRaisesRegex(ValueError, "replace it with settings") as raised,
        ):
            with runtime_environment("llm", True, "gemini"):
                self.fail("Invalid saved key was accepted")
            self.assertNotIn("READY_LLM_API_KEY", os.environ)
        self.assertNotIn("fixture\u200bkey", str(raised.exception))

    def test_offline_overrides_inherited_live_mode_and_restores_environment(self):
        with (
            patch.dict(os.environ, {"READY_AGENT_MODE": "llm", "READY_LLM_API_KEY": "test-only-secret"}),
            patch("scripts.ready.hidden_key", side_effect=AssertionError("No secret prompt offline")),
        ):
            with runtime_environment("offline", False):
                self.assertEqual(os.environ["READY_AGENT_MODE"], "offline")
                self.assertNotIn("READY_LLM_API_KEY", os.environ)
            self.assertEqual(os.environ["READY_AGENT_MODE"], "llm")
            self.assertEqual(os.environ["READY_LLM_API_KEY"], "test-only-secret")

    def test_live_requires_opt_in_before_key_prompt(self):
        with (
            patch("scripts.ready.hidden_key", side_effect=AssertionError("Must not prompt")),
            self.assertRaisesRegex(ValueError, "allow-network"),
            runtime_environment("llm", False),
        ):
            self.fail("Live mode entered without opt-in")

    def test_invalid_url_rejected_before_secret_prompt(self):
        with (
            patch.dict(os.environ, {"READY_LLM_BASE_URL": "http://untrusted.example/v1", "READY_LLM_MODEL": "test-model"}, clear=True),
            patch("scripts.ready.hidden_key", side_effect=AssertionError("Must validate first")),
            self.assertRaisesRegex(ValueError, "HTTPS"),
            runtime_environment("llm", True),
        ):
            self.fail("Invalid endpoint accepted")

    def test_transient_key_removed_after_error_without_output(self):
        config = {"READY_LLM_BASE_URL": "https://model.example.invalid/v1", "READY_LLM_MODEL": "test-model"}
        output = io.StringIO()
        with (
            patch.dict(os.environ, config, clear=True),
            redirect_stdout(output),
            patch("scripts.ready.hidden_key", return_value="test-only-secret"),
            self.assertRaises(RuntimeError),
        ):
            with runtime_environment("llm", True):
                self.assertEqual(os.environ["READY_LLM_API_KEY"], "test-only-secret")
                raise RuntimeError("Synthetic failure")
            self.assertNotIn("READY_LLM_API_KEY", os.environ)
            self.assertNotIn("READY_AGENT_MODE", os.environ)
        self.assertNotIn("test-only-secret", output.getvalue())

    def test_getpass_echo_fallback_is_rejected(self):
        def unavailable(_prompt):
            warnings.warn("Cannot hide input", getpass.GetPassWarning)
            self.fail("Fallback continued")

        with (
            patch("getpass.getpass", side_effect=unavailable),
            self.assertRaisesRegex(ValueError, "interactive local terminal"),
        ):
            hidden_key()

    def test_invalid_pasted_key_is_rejected_before_environment_storage(self):
        invalid_fixture = "fixture\u200bkey"
        with patch.dict(os.environ, {}, clear=True), patch("scripts.ready.hidden_key", return_value=invalid_fixture), patch("scripts.ready.backend_credentials.read_key", return_value=None):
            with self.assertRaisesRegex(ValueError, "non-ASCII") as raised:
                with runtime_environment("llm", True, "gemini"):
                    self.fail("Invalid credential was accepted")
            self.assertNotIn(invalid_fixture, str(raised.exception))
            self.assertNotIn("READY_LLM_API_KEY", os.environ)

    def test_settings_status_reports_presence_only(self):
        output = io.StringIO()
        with (
            patch("scripts.ready.backend_credentials.read_key", return_value="stored-test-only-key"),
            patch("scripts.ready.runpy.run_path", side_effect=AssertionError("Do not start")),
            redirect_stdout(output),
        ):
            self.assertEqual(main(["settings", "--provider", "gemini"]), 0)
        self.assertIn("saved", output.getvalue())
        self.assertNotIn("stored-test-only-key", output.getvalue())

    def test_settings_save_validates_before_writing_and_never_calls_model(self):
        output = io.StringIO()
        with (
            patch("scripts.ready.hidden_key", return_value="new-test-only-key"),
            patch("scripts.ready.backend_credentials.save_key") as save,
            patch("scripts.ready.runpy.run_path", side_effect=AssertionError("Do not start")),
            redirect_stdout(output),
        ):
            self.assertEqual(main(["settings", "--provider", "gemini", "--set-key"]), 0)
            save.assert_called_once_with("new-test-only-key")
        self.assertNotIn("new-test-only-key", output.getvalue())

    def test_settings_rejects_invalid_key_before_writing(self):
        output = io.StringIO()
        with (
            patch("scripts.ready.hidden_key", return_value="fixture\u200bkey"),
            patch("scripts.ready.backend_credentials.save_key", side_effect=AssertionError("Must not write")),
            redirect_stdout(output),
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            self.assertEqual(main(["settings", "--provider", "gemini", "--set-key"]), 2)
        self.assertIn("non-ASCII", stderr.getvalue())
        self.assertNotIn("fixture\u200bkey", stderr.getvalue())

    def test_settings_cannot_be_combined_with_network_or_server(self):
        with (
            patch("scripts.ready.hidden_key", side_effect=AssertionError("Must not prompt")),
            redirect_stdout(io.StringIO()),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            with self.assertRaises(SystemExit):
                main(["settings", "--provider", "gemini", "--allow-network", "--set-key"])
            with self.assertRaises(SystemExit):
                main(["serve", "--set-key"])

    def test_check_never_starts_backend_or_prompts(self):
        with (
            patch("scripts.ready.runpy.run_path", side_effect=AssertionError("Do not start")),
            patch("scripts.ready.hidden_key", side_effect=AssertionError("Do not prompt")),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(["check"]), 0)

    def test_smoke_limit_cannot_accidentally_expand(self):
        with self.assertRaises(SystemExit):
            main(["smoke", "--limit", "200"])
