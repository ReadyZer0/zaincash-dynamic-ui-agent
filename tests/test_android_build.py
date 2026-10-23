"""Build safety/provenance tests that do not require a downloaded Android SDK."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from scripts.build_android import (
    ANDROID,
    badging_matches_contract,
    manifest_contract,
    new_build_directory,
    publish_outputs,
    source_snapshot,
    validate_dex,
)


def checked_dex(data: bytearray) -> bytes:
    data[12:32] = hashlib.sha1(data[32:]).digest()
    struct.pack_into("<I", data, 8, zlib.adler32(data[12:]) & 0xFFFFFFFF)
    return bytes(data)


class AndroidBuildTests(unittest.TestCase):
    def test_badging_accepts_aapt2_min_sdk_spelling_without_skipping_contract(self) -> None:
        contract = manifest_contract(ANDROID / "app/src/main/AndroidManifest.xml")
        base = (
            "package: name='iq.ready.billpay.demo' versionCode='1' versionName='0.2.0-demo'\n"
            "targetSdkVersion:'35'\n"
        )
        self.assertTrue(badging_matches_contract(base + "minSdkVersion:'26'\n", contract))
        self.assertTrue(badging_matches_contract(base + "sdkVersion:'26'\n", contract))
        self.assertFalse(badging_matches_contract(base + "minSdkVersion:'25'\n", contract))
        self.assertFalse(badging_matches_contract(base.replace("versionCode='1'", "versionCode='2'") + "minSdkVersion:'26'\n", contract))

    def test_manifest_version_and_contract_come_from_source(self) -> None:
        contract = manifest_contract(ANDROID / "app/src/main/AndroidManifest.xml")
        self.assertEqual(contract["package"], "iq.ready.billpay.demo")
        self.assertEqual(contract["min_android_api"], 26)
        self.assertEqual(contract["target_android_api"], 35)
        self.assertTrue(contract["version"])
        self.assertGreater(contract["version_code"], 0)

    def test_build_does_not_delete_previous_outputs_or_unrelated_files(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            android = Path(folder) / "android"
            previous = android / "build/outputs/old.apk"
            previous.parent.mkdir(parents=True)
            previous.write_bytes(b"keep-existing-apk")
            first = new_build_directory(android)
            second = new_build_directory(android)
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertEqual(previous.read_bytes(), b"keep-existing-apk")

    def test_publish_preserves_old_pair_and_per_run_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            android = Path(folder) / "android"
            build = new_build_directory(android)
            old = android / "build/outputs"
            old.mkdir()
            names = ("AliDheaa_Topic04_READY_Debug.apk", "build-info.json")
            for name in names:
                (old / name).write_bytes(b"previous")
                (build / "outputs" / name).write_bytes(b"verified-new")
            published = publish_outputs(build, android)
            for name in names:
                self.assertEqual((published / name).read_bytes(), b"verified-new")
                self.assertEqual((build / "outputs" / name).read_bytes(), b"verified-new")
                self.assertEqual((build / "previous-outputs" / name).read_bytes(), b"previous")

    def test_publication_rejects_path_outside_build_root(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, "outside"):
                publish_outputs(root / "unexpected", root / "android")

    def test_incomplete_build_cannot_replace_a_previous_apk(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            android = Path(folder) / "android"
            build = new_build_directory(android)
            old = android / "build/outputs"
            old.mkdir()
            name = "AliDheaa_Topic04_READY_Debug.apk"
            (old / name).write_bytes(b"previous")
            (build / "outputs" / name).write_bytes(b"not-fully-verified")
            with self.assertRaisesRegex(ValueError, "Both verified outputs"):
                publish_outputs(build, android)
            self.assertEqual((old / name).read_bytes(), b"previous")

    def test_dex_checks_reject_corruption_and_invalid_table_bounds(self) -> None:
        data = bytearray(112)
        data[:8] = b"dex\n035\x00"
        struct.pack_into("<III", data, 32, 112, 112, 0x12345678)
        valid = checked_dex(data)
        self.assertEqual(validate_dex(valid)["version"], "035")
        with self.assertRaisesRegex(ValueError, "header"):
            validate_dex(valid[:100])
        corrupt = bytearray(valid)
        corrupt[12] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            validate_dex(corrupt)
        struct.pack_into("<II", data, 56, 5, 112)
        with self.assertRaisesRegex(ValueError, "table bounds"):
            validate_dex(checked_dex(data))

    def test_fingerprint_changes_with_app_source_but_not_local_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "android/app/src/main/AndroidManifest.xml"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"source-v1")
            with patch("scripts.build_android.subprocess.run", side_effect=OSError):
                first = source_snapshot(root)
                (root / ".env").write_bytes(b"not-a-real-key")
                second = source_snapshot(root)
                self.assertEqual(first["android_source_sha256"], second["android_source_sha256"])
                self.assertIsNone(first["git_commit"])
                self.assertIsNone(first["working_tree_dirty"])
                self.assertNotIn(".env", first["fingerprint_files"])
                source.write_bytes(b"source-v2")
                third = source_snapshot(root)
                self.assertNotEqual(first["android_source_sha256"], third["android_source_sha256"])


if __name__ == "__main__":
    unittest.main()
