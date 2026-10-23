"""Foreground READY launcher; offline default, no key files or background services."""

from __future__ import annotations

import argparse
import getpass
import os
import runpy
import sqlite3
import sys
import warnings
from contextlib import closing, contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import backend_credentials
from llm_agent import GEMINI_BASE_URL, GEMINI_FLASH_MODEL, LLMConfig


def prerequisites() -> list[tuple[str, bool, str]]:
    checks = [("Python 3.12+", sys.version_info >= (3, 12), "Install Python 3.12 or newer.")]
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("SELECT 1").fetchone()
        checks.append(("SQLite", True, ""))
    except sqlite3.Error:
        checks.append(("SQLite", False, "Use a Python build with SQLite support."))
    try:
        ZoneInfo("Asia/Baghdad")
        checks.append(("Baghdad timezone data", True, ""))
    except ZoneInfoNotFoundError:
        checks.append(("Baghdad timezone data", False, "Run: python -m pip install tzdata (needed on Windows without IANA timezone data)."))
    files_present = all((REPO / name).is_file() for name in ("server.py", "web/index.html", "evaluation/run.py"))
    checks.append(("Repository files", files_present, "Run this launcher from a complete READY checkout."))
    return checks


def hidden_key(prompt: str = "Backend model API key (hidden, process only): ") -> str:
    # getpass otherwise falls back to echoed stdin on unsupported terminals.
    # Fail closed instead of accidentally displaying a credential.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt).strip()
    except (getpass.GetPassWarning, EOFError) as error:
        raise ValueError("Hidden key entry is unavailable. Use an interactive local terminal; never paste the key into chat.") from error


@contextmanager
def runtime_environment(mode: str, allow_network: bool, provider: str = "custom"):
    names = ("READY_AGENT_MODE", "READY_LLM_API_KEY", "READY_LLM_BASE_URL", "READY_LLM_MODEL",
             "READY_LLM_REQUEST_CAP", "READY_LLM_ENABLE_THINKING")
    original = {name: os.environ.get(name) for name in names}
    try:
        if provider == "gemini":
            if mode != "llm":
                raise ValueError("The Gemini preset requires --mode llm.")
            os.environ["READY_LLM_BASE_URL"] = GEMINI_BASE_URL
            os.environ["READY_LLM_MODEL"] = GEMINI_FLASH_MODEL
            os.environ["READY_LLM_REQUEST_CAP"] = "5"
            # This vendor-specific flag may be left over from a different
            # compatible provider and is not part of the Gemini preset.
            os.environ.pop("READY_LLM_ENABLE_THINKING", None)
            # Do not reuse an inherited or accidentally exposed credential.
            os.environ.pop("READY_LLM_API_KEY", None)
        elif provider != "custom":
            raise ValueError("Unsupported provider preset.")
        if mode == "llm" and not allow_network:
            raise ValueError("Live mode requires --allow-network and an approved provider/quota; it sends synthetic requests to that provider.")
        os.environ["READY_AGENT_MODE"] = mode
        if mode == "offline":
            os.environ.pop("READY_LLM_API_KEY", None)
        else:
            # Validate public configuration before asking for any secret.
            preview = dict(os.environ)
            preview["READY_LLM_API_KEY"] = "preflight-placeholder-not-a-credential"
            if error := LLMConfig.from_env(preview).configuration_error():
                raise ValueError(error)
            if not os.environ.get("READY_LLM_API_KEY"):
                entered_key = backend_credentials.read_key() if provider == "gemini" and sys.platform == "win32" else None
                from_store = entered_key is not None
                if entered_key is None:
                    entered_key = hidden_key()
                candidate = dict(os.environ)
                candidate["READY_LLM_API_KEY"] = entered_key
                if error := LLMConfig.from_env(candidate).configuration_error():
                    if from_store:
                        raise ValueError("The saved Gemini key is invalid; replace it with settings --provider gemini --set-key.")
                    raise ValueError(error)
                os.environ["READY_LLM_API_KEY"] = entered_key
            if error := LLMConfig.from_env().configuration_error():
                raise ValueError(error)
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def manage_gemini_key(set_key: bool, clear_key: bool) -> None:
    """Manage only the backend Windows credential; never contact a provider."""
    if set_key:
        if sys.platform != "win32":
            raise ValueError("Saved Gemini keys are supported only on Windows; use the hidden per-run prompt here.")
        entered_key = hidden_key("Gemini API key (hidden; save for this Windows user): ")
        candidate = LLMConfig(mode="llm", base_url=GEMINI_BASE_URL,
                              model=GEMINI_FLASH_MODEL, api_key=entered_key, request_cap=5)
        if error := candidate.configuration_error():
            raise ValueError(error)
        backend_credentials.save_key(entered_key)
        print("Gemini key saved in Windows Credential Manager for this user. No model request was made.")
    elif clear_key:
        removed = backend_credentials.delete_key()
        print("Saved Gemini key removed." if removed else "No saved Gemini key was present.")
    else:
        present = backend_credentials.read_key() is not None
        print("Gemini key: saved for this Windows user." if present else "Gemini key: not saved. No model request was made.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "serve", "smoke", "settings"))
    parser.add_argument("--mode", choices=("offline", "llm"), default="offline")
    parser.add_argument("--provider", choices=("custom", "gemini"), default="custom")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--limit", type=int, default=5, help="Smoke cases, 1–5; use the full evaluator separately for larger approved runs")
    key_actions = parser.add_mutually_exclusive_group()
    key_actions.add_argument("--set-key", action="store_true", help="Save a Gemini key via hidden prompt in Windows Credential Manager")
    key_actions.add_argument("--clear-key", action="store_true", help="Remove only READY's saved Gemini key")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 5:
        parser.error("--limit must be between 1 and 5")
    if args.command != "settings" and (args.set_key or args.clear_key):
        parser.error("--set-key and --clear-key are only available with settings")
    if args.command == "settings":
        if args.provider != "gemini" or args.mode != "offline" or args.allow_network:
            parser.error("Gemini settings require --provider gemini and do not accept live/network flags")
        try:
            manage_gemini_key(args.set_key, args.clear_key)
            return 0
        except ValueError as error:
            print(f"Setup error: {error}", file=sys.stderr)
            return 2
    checks = prerequisites()
    for name, ok, remedy in checks:
        print(f"{'OK' if ok else 'MISSING'}: {name}" + (f" — {remedy}" if not ok else ""))
    if not all(ok for _, ok, _ in checks):
        return 1
    if args.command == "check":
        print("No server started, no model call made, no device changed. Android prerequisites: see docs/ANDROID.md.")
        return 0
    try:
        with runtime_environment(args.mode, args.allow_network, args.provider):
            print("OFFLINE_DEMO: no model calls." if args.mode == "offline" else "LIVE_MODEL configured: compatibility still requires a successful request. Provider usage is bounded by the configured limits, not free by assumption.")
            if args.command == "serve":
                print("Foreground only. Stop with Ctrl+C. USB setup: adb reverse tcp:8765 tcp:8765")
                runpy.run_path(str(REPO / "server.py"), run_name="__main__")
                return 0
            from evaluation.run import main as evaluate

            evaluation_args = ["--mode", args.mode, "--limit", str(args.limit)]
            if args.allow_network:
                evaluation_args.append("--allow-network")
            return evaluate(evaluation_args)
    except ValueError as error:
        print(f"Setup error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
