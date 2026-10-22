"""Windows credential boundary tests use synthetic names and never real keys."""

from __future__ import annotations

import os
import sys
import unittest
import uuid
from unittest.mock import patch

import backend_credentials


class BackendCredentialTests(unittest.TestCase):
    def test_invalid_secret_never_reaches_windows_store(self):
        with patch("backend_credentials._api", side_effect=AssertionError("No store call")):
            with self.assertRaisesRegex(ValueError, "non-ASCII"):
                backend_credentials.save_key("fixture\u200bkey")
            with self.assertRaisesRegex(ValueError, "too long"):
                backend_credentials.save_key("x" * 2561)

    @unittest.skipUnless(
        sys.platform == "win32" and os.environ.get("READY_TEST_WIN_CREDENTIALS") == "1",
        "opt-in Windows Credential Manager roundtrip",
    )
    def test_synthetic_credential_roundtrip(self):
        target = f"ReadyZer0_READY_Demo_Test_{uuid.uuid4().hex}"
        with patch.object(backend_credentials, "TARGET", target):
            self.assertIsNone(backend_credentials.read_key())
            try:
                backend_credentials.save_key("synthetic-test-only-key")
                self.assertEqual(backend_credentials.read_key(), "synthetic-test-only-key")
            finally:
                backend_credentials.delete_key()
            self.assertIsNone(backend_credentials.read_key())


if __name__ == "__main__":
    unittest.main()
