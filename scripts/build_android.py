#!/usr/bin/env python3
"""Build the small Android demo with official SDK tools; no Gradle download needed.

Install JDK 17+, Android SDK platform 35 and build-tools 35.0.0 first. Set
READY_ANDROID_SDK to your SDK directory, or pass --sdk. All generated files,
including the local debug signing key, stay under ignored android/ directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", default=os.environ.get("READY_ANDROID_SDK") or os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME"))
    parser.add_argument("--build-tools", default="35.0.0")
    parser.add_argument("--platform", default="35")
    args = parser.parse_args()
    if not args.sdk:
        parser.error("Pass --sdk PATH or set READY_ANDROID_SDK to your installed Android SDK.")
    sdk = Path(args.sdk).expanduser().resolve()
    build_tools = sdk / "build-tools" / args.build_tools
    android_jar = sdk / "platforms" / f"android-{args.platform}" / "android.jar"
    if not android_jar.is_file():
        raise SystemExit(f"Install platforms;android-{args.platform}; missing {android_jar}")
    java = shutil.which("java")
    keytool = shutil.which("keytool")
    if not java or not keytool:
        raise SystemExit("Install JDK 17+ and put java and keytool on PATH.")
    aapt2 = str(executable(build_tools, "aapt2"))
    zipalign = str(executable(build_tools, "zipalign"))
    d8_jar = build_tools / "lib" / "d8.jar"
    signer_jar = build_tools / "lib" / "apksigner.jar"
    for needed in (d8_jar, signer_jar):
        if not needed.is_file():
            raise SystemExit(f"Missing Android SDK component: {needed}")

    build = ANDROID / "build"
    if build.exists():
        shutil.rmtree(build)
    for folder in ("generated", "classes", "policy-tests", "dex", "outputs"):
        (build / folder).mkdir(parents=True, exist_ok=True)

    source = ANDROID / "app" / "src" / "main"
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
    run([java, "-cp", str(d8_jar), "com.android.tools.r8.D8", "--min-api", "26", "--lib", str(android_jar), "--output", str(build / "dex"), str(classes_jar)])
    with zipfile.ZipFile(unsigned, "a") as archive:
        for path in sorted((build / "dex").glob("*.dex")):
            archive.write(path, path.name, compress_type=zipfile.ZIP_STORED)
    run([zipalign, "-f", "-p", "4", str(unsigned), str(aligned)])

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
    run([zipalign, "-c", "-p", "4", str(output)])
    manifest = run([aapt2, "dump", "badging", str(output)], capture=True)
    print(manifest.strip())
    if "name='iq.ready.billpay.demo'" not in manifest or "minSdkVersion:'26'" not in manifest or "targetSdkVersion:'35'" not in manifest:
        raise SystemExit("Unexpected APK manifest; build did not meet the declared package/API contract.")
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or "classes.dex" not in archive.namelist():
            raise SystemExit("APK ZIP/DEX validation failed.")
    report = {
        "artifact": output.name,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "size_bytes": output.stat().st_size,
        "package": "iq.ready.billpay.demo",
        "version": "0.2.0-demo",
        "min_android_api": 26,
        "target_android_api": 35,
        "compile_platform": args.platform,
        "build_tools": args.build_tools,
        "signature_verification": verification.strip(),
        "endpoint_policy_tests": policy_result.strip(),
        "on_device_test": "NOT_RUN: no physical Android device or emulator available in this build environment",
        "model_api_key_in_apk": False,
        "backend_required": True,
    }
    (build / "outputs" / "build-info.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nAPK: {output}\nSHA-256: {report['sha256']}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout, file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        raise SystemExit(error.returncode) from error
