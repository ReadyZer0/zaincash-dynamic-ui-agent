#!/usr/bin/env python3
"""Build the small Android demo with official SDK tools; no Gradle download needed.

Install JDK 17+, Android SDK platform 35 and build-tools 35.0.0 first. Set
READY_ANDROID_SDK to your SDK directory, or pass --sdk. All generated files,
including the local debug signing key, stay under ignored android/ directories.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib


REPO = Path(__file__).resolve().parents[1]
ANDROID = REPO / "android"


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(command, check=True, text=True, capture_output=capture)
    return result.stdout if capture else ""


def executable(directory: Path, name: str) -> Path:
    path = directory / (name + (".exe" if os.name == "nt" else ""))
    if not path.is_file():
        raise SystemExit(f"Missing Android SDK tool: {path}")
    return path


def manifest_contract(path: Path) -> dict:
    """Read version/API facts from the actual manifest, not duplicated constants."""
    root = ET.parse(path).getroot()
    namespace = "{http://schemas.android.com/apk/res/android}"
    sdk = root.find("uses-sdk")
    if sdk is None:
        raise ValueError("Manifest must declare uses-sdk")
    result = {
        "package": root.attrib["package"],
        "version": root.attrib[namespace + "versionName"],
        "version_code": int(root.attrib[namespace + "versionCode"]),
        "min_android_api": int(sdk.attrib[namespace + "minSdkVersion"]),
        "target_android_api": int(sdk.attrib[namespace + "targetSdkVersion"]),
    }
    if result["package"] != "iq.ready.billpay.demo" or result["min_android_api"] != 26 or result["target_android_api"] != 35:
        raise ValueError("Unexpected package/API contract")
    return result


def badging_matches_contract(badging: str, contract: dict) -> bool:
    """Accept the two SDK field spellings emitted by supported AAPT2 builds."""
    required = (
        f"name='{contract['package']}'",
        f"versionName='{contract['version']}'",
        f"versionCode='{contract['version_code']}'",
        f"targetSdkVersion:'{contract['target_android_api']}'",
    )
    minimum = contract["min_android_api"]
    return all(item in badging for item in required) and any(
        item in badging for item in (f"sdkVersion:'{minimum}'", f"minSdkVersion:'{minimum}'")
    )


def source_snapshot(repo: Path) -> dict:
    """Record provenance without reading credentials, local databases or outputs."""
    def git(*args: str) -> str | None:
        try:
            process = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=True)
            return process.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    paths = sorted((repo / "android/app/src/main").rglob("*"))
    paths += sorted((repo / "android/tests").rglob("*.java"))
    paths.append(repo / "scripts/build_android.py")
    digest = hashlib.sha256()
    files = []
    for path in sorted(paths):
        if not path.is_file():
            continue
        relative = path.relative_to(repo).as_posix()
        digest.update(relative.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
        files.append(relative)
    status = git("status", "--porcelain", "--untracked-files=normal")
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_branch": git("branch", "--show-current"),
        "working_tree_dirty": bool(status) if status is not None else None,
        "android_source_sha256": digest.hexdigest(),
        "fingerprint_files": files,
        "scope": "Android app sources/resources, endpoint policy tests and build script; backend/web are fetched at runtime and not bundled",
    }


def new_build_directory(android: Path) -> Path:
    """Never recursively erase the build root or replace an existing artifact."""
    root = android.resolve()
    build_root = (android / "build").resolve()
    if build_root.parent != root:
        raise ValueError("Android build directory must stay inside the Android project")
    build_root.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix="run-", dir=build_root))
    for folder in ("generated", "classes", "policy-tests", "dex", "outputs"):
        (build / folder).mkdir()
    return build


def validate_dex(data: bytes) -> dict:
    """Check standard DEX header, hashes and table bounds, not runtime behavior."""
    if len(data) < 112 or not re.fullmatch(rb"dex\n0(?:35|37|38|39|40)\x00", data[:8]):
        raise ValueError("Unsupported or truncated DEX header")
    checksum, = struct.unpack_from("<I", data, 8)
    file_size, header_size, endian = struct.unpack_from("<III", data, 32)
    if file_size != len(data) or header_size != 112 or endian != 0x12345678:
        raise ValueError("Invalid DEX length/header/endian tag")
    if hashlib.sha1(data[32:]).digest() != data[12:32] or zlib.adler32(data[12:]) & 0xFFFFFFFF != checksum:
        raise ValueError("DEX checksum/signature mismatch")
    for name, header_offset, item_size in (
        ("strings", 56, 4), ("types", 64, 4), ("prototypes", 72, 12),
        ("fields", 80, 8), ("methods", 88, 8), ("classes", 96, 32),
    ):
        count, offset = struct.unpack_from("<II", data, header_offset)
        if count and (offset < header_size or offset % 4 or offset + count * item_size > file_size):
            raise ValueError(f"Invalid DEX {name} table bounds")
        if not count and offset:
            raise ValueError(f"Empty DEX {name} table has an offset")
    data_size, data_offset = struct.unpack_from("<II", data, 104)
    if data_size and (data_offset < header_size or data_offset + data_size > file_size):
        raise ValueError("Invalid DEX data section bounds")
    return {"version": data[4:7].decode("ascii"), "size_bytes": len(data), "header_hashes_table_bounds": "passed"}


def publish_outputs(build: Path, android: Path) -> Path:
    """Keep per-run outputs; archive any previous convenience copy before update."""
    root = (android / "build").resolve()
    if build.resolve().parent != root:
        raise ValueError("Build is outside the Android build root")
    outputs = android / "build" / "outputs"
    if outputs.resolve().parent != root:
        raise ValueError("Output directory points outside the Android build root")
    names = ("AliDheaa_Topic04_READY_Debug.apk", "build-info.json")
    for name in names:
        if not (build / "outputs" / name).is_file():
            raise ValueError("Both verified outputs are required before publication")
        if (outputs / name).is_symlink():
            raise ValueError("Refusing to replace a symlinked output")
        temporary = outputs / (name + ".pending")
        if temporary.exists() or temporary.is_symlink():
            raise ValueError("An interrupted publication is present; inspect .pending output first")
    outputs.mkdir(exist_ok=True)
    for name in names:
        target = outputs / name
        if target.exists():
            backup = build / "previous-outputs"
            backup.mkdir(exist_ok=True)
            shutil.copy2(target, backup / name)
        temporary = outputs / (name + ".pending")
        shutil.copy2(build / "outputs" / name, temporary)
        os.replace(temporary, target)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", default=os.environ.get("READY_ANDROID_SDK") or os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME"))
    parser.add_argument("--build-tools", default="35.0.0")
    parser.add_argument("--platform", default="35")
    parser.add_argument("--jdk", default=os.environ.get("JAVA_HOME"), help="Optional JDK directory; no system PATH change needed")
    args = parser.parse_args()
    if not args.sdk:
        parser.error("Pass --sdk PATH or set READY_ANDROID_SDK to your installed Android SDK.")
    sdk = Path(args.sdk).expanduser().resolve()
    build_tools = sdk / "build-tools" / args.build_tools
    android_jar = sdk / "platforms" / f"android-{args.platform}" / "android.jar"
    if not android_jar.is_file():
        raise SystemExit(f"Install platforms;android-{args.platform}; missing {android_jar}")
    java = str(executable(Path(args.jdk) / "bin", "java")) if args.jdk else shutil.which("java")
    keytool = str(executable(Path(args.jdk) / "bin", "keytool")) if args.jdk else shutil.which("keytool")
    if not java or not keytool:
        raise SystemExit("Install JDK 17+ and put java and keytool on PATH.")
    aapt2 = str(executable(build_tools, "aapt2"))
    zipalign = str(executable(build_tools, "zipalign"))
    d8_jar = build_tools / "lib" / "d8.jar"
    signer_jar = build_tools / "lib" / "apksigner.jar"
    for needed in (d8_jar, signer_jar):
        if not needed.is_file():
            raise SystemExit(f"Missing Android SDK component: {needed}")

    source = ANDROID / "app" / "src" / "main"
    contract = manifest_contract(source / "AndroidManifest.xml")
    provenance = source_snapshot(REPO)
    java_version = subprocess.run([java, "-version"], check=True, text=True, capture_output=True)
    compiler_modules = run([java, "--list-modules"], capture=True)
    if not any(line.startswith("jdk.compiler@") for line in compiler_modules.splitlines()):
        raise SystemExit("A full JDK with the jdk.compiler module is required.")
    build = new_build_directory(ANDROID)
    javac = [java, "-m", "jdk.compiler/com.sun.tools.javac.Main", "--release", "8", "-encoding", "UTF-8"]
    run(javac + ["-d", str(build / "policy-tests"), str(source / "java/iq/ready/billpay/demo/EndpointPolicy.java"), str(ANDROID / "tests/EndpointPolicyTest.java")])
    policy_result = run([java, "-cp", str(build / "policy-tests"), "iq.ready.billpay.demo.EndpointPolicyTest"], capture=True)
    print(policy_result.strip())

    resources = build / "resources.zip"
    unsigned = build / "unsigned.apk"
    aligned = build / "aligned.apk"
    output = build / "outputs" / "AliDheaa_Topic04_READY_Debug.apk"
    run([aapt2, "compile", "--dir", str(source / "res"), "-o", str(resources)])
    run([aapt2, "link", "-o", str(unsigned), "-I", str(android_jar), "--manifest", str(source / "AndroidManifest.xml"), "--java", str(build / "generated"), str(resources)])
    java_sources = sorted((source / "java").rglob("*.java")) + sorted((build / "generated").rglob("*.java"))
    run(javac + ["-classpath", str(android_jar), "-d", str(build / "classes")] + [str(path) for path in java_sources])
    classes_jar = build / "classes.jar"
    with zipfile.ZipFile(classes_jar, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((build / "classes").rglob("*.class")):
            archive.write(path, path.relative_to(build / "classes").as_posix())
    run([java, "-cp", str(d8_jar), "com.android.tools.r8.D8", "--min-api", str(contract["min_android_api"]), "--lib", str(android_jar), "--output", str(build / "dex"), str(classes_jar)])
    with zipfile.ZipFile(unsigned, "a") as archive:
        for path in sorted((build / "dex").glob("*.dex")):
            archive.write(path, path.name, compress_type=zipfile.ZIP_STORED)
    run([zipalign, "-f", "-P", "16", "4", str(unsigned), str(aligned)])

    local = ANDROID / ".local"
    local.mkdir(exist_ok=True)
    keystore = local / "debug.keystore"
    if not keystore.exists():
        run([keytool, "-genkeypair", "-keystore", str(keystore), "-storetype", "JKS", "-storepass", "android", "-keypass", "android", "-alias", "androiddebugkey", "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000", "-dname", "CN=Android Debug, O=READY Demo, C=IQ"])
        if os.name != "nt":
            keystore.chmod(0o600)
    run([java, "-jar", str(signer_jar), "sign", "--ks", str(keystore), "--ks-key-alias", "androiddebugkey", "--ks-pass", "pass:android", "--key-pass", "pass:android", "--out", str(output), str(aligned)])
    verification = run([java, "-jar", str(signer_jar), "verify", "--verbose", "--print-certs", str(output)], capture=True)
    print(verification.strip())
    run([zipalign, "-c", "-P", "16", "4", str(output)])
    manifest = run([aapt2, "dump", "badging", str(output)], capture=True)
    print(manifest.strip())
    if not badging_matches_contract(manifest, contract):
        raise SystemExit("Unexpected APK manifest; build did not meet the declared package/API contract.")
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or "classes.dex" not in archive.namelist():
            raise SystemExit("APK ZIP/DEX validation failed.")
        dex_results = {name: validate_dex(archive.read(name)) for name in archive.namelist() if re.fullmatch(r"classes(?:[2-9]|[1-9][0-9]+)?\.dex", name)}
    report = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": provenance,
        "artifact": output.name,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "size_bytes": output.stat().st_size,
        **contract,
        "compile_platform": args.platform,
        "build_tools": args.build_tools,
        "java_version": (java_version.stdout + java_version.stderr).strip(),
        "zip_alignment": "passed: 4-byte entries, 16-KiB shared-library alignment",
        "dex_validation": dex_results,
        "signature_verification": verification.strip(),
        "endpoint_policy_tests": policy_result.strip(),
        "on_device_test": "NOT_RUN by this build script; installation/launch requires a separate dated device report",
        "model_api_key_in_apk": False,
        "backend_required": True,
    }
    (build / "outputs" / "build-info.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    published = publish_outputs(build, ANDROID)
    print(f"\nAPK: {published / output.name}\nSHA-256: {report['sha256']}\nPreserved build: {build}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout, file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        raise SystemExit(error.returncode) from error
