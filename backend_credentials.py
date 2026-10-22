"""Backend-only Gemini credential storage for the current Windows user.

No browser, Android, SQLite, repository file, or model tool can access this
module. Windows Credential Manager owns persistence; only the foreground
backend launcher reads the credential when live mode is explicitly selected.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

TARGET = "ReadyZer0_READY_Demo_Gemini_API"
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168
_MAX_BLOB_BYTES = 2560


class CredentialStoreError(ValueError):
    """A safe user-facing error that never contains credential material."""


class _FILETIME(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", wintypes.LPBYTE),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _api():
    if sys.platform != "win32":
        raise CredentialStoreError("Saved Gemini keys are supported only on Windows; use the hidden per-run prompt here.")
    api = ctypes.WinDLL("Advapi32", use_last_error=True)
    api.CredReadW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)))
    api.CredReadW.restype = wintypes.BOOL
    api.CredWriteW.argtypes = (ctypes.POINTER(_CREDENTIALW), wintypes.DWORD)
    api.CredWriteW.restype = wintypes.BOOL
    api.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
    api.CredDeleteW.restype = wintypes.BOOL
    api.CredFree.argtypes = (ctypes.c_void_p,)
    api.CredFree.restype = None
    return api


def read_key() -> str | None:
    """Return the current user's saved key, or None when no key exists."""
    api = _api()
    entry = ctypes.POINTER(_CREDENTIALW)()
    if not api.CredReadW(TARGET, _CRED_TYPE_GENERIC, 0, ctypes.byref(entry)):
        if ctypes.get_last_error() == _ERROR_NOT_FOUND:
            return None
        raise CredentialStoreError("Windows Credential Manager could not read the saved Gemini key.")
    try:
        credential = entry.contents
        size = credential.CredentialBlobSize
        if not 0 < size <= _MAX_BLOB_BYTES or not credential.CredentialBlob:
            raise CredentialStoreError("The saved Gemini key is invalid; replace it in backend settings.")
        try:
            return ctypes.string_at(credential.CredentialBlob, size).decode("ascii")
        except UnicodeDecodeError as error:
            raise CredentialStoreError("The saved Gemini key is invalid; replace it in backend settings.") from error
    finally:
        api.CredFree(entry)


def save_key(key: str) -> None:
    """Replace the Gemini key for this Windows user without writing a file."""
    if not key or not key.isascii() or any(ord(char) < 32 for char in key):
        raise CredentialStoreError("The API credential contains non-ASCII or control characters. Enter only the raw key.")
    if len(key) > _MAX_BLOB_BYTES:
        raise CredentialStoreError("The API credential is too long for Windows Credential Manager.")
    blob = bytearray(key, "ascii")
    try:
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer(blob)
        credential = _CREDENTIALW()
        credential.Type = _CRED_TYPE_GENERIC
        credential.TargetName = TARGET
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, wintypes.LPBYTE)
        credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
        if not _api().CredWriteW(ctypes.byref(credential), 0):
            raise CredentialStoreError("Windows Credential Manager could not save the Gemini key.")
    finally:
        for index in range(len(blob)):
            blob[index] = 0


def delete_key() -> bool:
    """Delete only READY's named Gemini key. Return False if it was absent."""
    api = _api()
    if api.CredDeleteW(TARGET, _CRED_TYPE_GENERIC, 0):
        return True
    if ctypes.get_last_error() == _ERROR_NOT_FOUND:
        return False
    raise CredentialStoreError("Windows Credential Manager could not remove the Gemini key.")
