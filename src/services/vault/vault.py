"""Encrypted per-profile account secrets (password, 2FA key, backup codes...).

Secrets are stored in profiles.json as `FPV1:` tokens (scrypt + AES-256-GCM), never as
plain text, and travel with the profile through export and sync. The passphrase comes
from the OS credential store (Windows Credential Manager, macOS Keychain, Secret
Service) and falls back to FOXPROFILE_SYNC_PASSPHRASE / FOXPROFILE_VAULT_PASSPHRASE, which
is what a VPS uses. It is the same passphrase that encrypts synced archives.
"""

from __future__ import annotations

import base64
import contextlib
import hmac
import os
import struct
import threading
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

PREFIX = "FPV1:"
SECRET_FIELDS = ("password", "totp_secret", "backup_codes", "recovery", "hint")
SERVICE = "foxprofile"
KEY_NAME = "vault-passphrase"

_session_passphrase: str | None = None
_lock = threading.Lock()


class VaultError(Exception):
    pass


class VaultLocked(VaultError):
    pass


def _keyring():
    try:
        import keyring

        return keyring
    except ImportError:
        return None


def get_passphrase() -> str:
    """Session value, then the OS credential store, then the environment."""
    with _lock:
        if _session_passphrase:
            return _session_passphrase
    kr = _keyring()
    if kr is not None:
        try:
            stored = kr.get_password(SERVICE, KEY_NAME)
            if stored:
                return stored
        except Exception:  # noqa: BLE001  (no usable backend on a headless box)
            pass
    return os.getenv("FOXPROFILE_VAULT_PASSPHRASE") or os.getenv("FOXPROFILE_SYNC_PASSPHRASE", "")


def set_passphrase(passphrase: str, persist: bool = True) -> str:
    """Use `passphrase` now; with persist, also keep it in the OS credential store.
    Returns where it was kept: keyring or session."""
    global _session_passphrase
    if not passphrase:
        raise VaultError("passphrase is empty")
    with _lock:
        _session_passphrase = passphrase
    if persist and (kr := _keyring()) is not None:
        try:
            kr.set_password(SERVICE, KEY_NAME, passphrase)
            return "keyring"
        except Exception:  # noqa: BLE001
            pass
    return "session"


def clear_passphrase() -> None:
    global _session_passphrase
    with _lock:
        _session_passphrase = None
    if (kr := _keyring()) is not None:
        with contextlib.suppress(Exception):
            kr.delete_password(SERVICE, KEY_NAME)


def is_unlocked() -> bool:
    return bool(get_passphrase())


def _derive(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(passphrase.encode("utf-8"))


def encrypt(text: str, passphrase: str | None = None) -> str:
    passphrase = passphrase or get_passphrase()
    if not passphrase:
        raise VaultLocked("Vault is locked: set the passphrase first")
    salt, nonce = os.urandom(16), os.urandom(12)
    blob = AESGCM(_derive(passphrase, salt)).encrypt(nonce, text.encode("utf-8"), b"fpv1")
    return PREFIX + base64.urlsafe_b64encode(salt + nonce + blob).decode()


def decrypt(token: str, passphrase: str | None = None) -> str:
    passphrase = passphrase or get_passphrase()
    if not passphrase:
        raise VaultLocked("Vault is locked: set the passphrase first")
    if not token.startswith(PREFIX):
        raise VaultError("not an encrypted secret")
    raw = base64.urlsafe_b64decode(token[len(PREFIX) :])
    salt, nonce, blob = raw[:16], raw[16:28], raw[28:]
    try:
        return AESGCM(_derive(passphrase, salt)).decrypt(nonce, blob, b"fpv1").decode("utf-8")
    except InvalidTag as e:
        raise VaultError("wrong passphrase for this secret") from e


def totp(secret: str, at: float | None = None, digits: int = 6, step: int = 30) -> tuple[str, int]:
    """RFC 6238 code and the seconds it stays valid. `secret` is the base32 key
    (spaces and case ignored) shown when setting up an authenticator app."""
    cleaned = "".join(secret.split()).upper()
    cleaned += "=" * (-len(cleaned) % 8)
    try:
        key = base64.b32decode(cleaned)
    except Exception as e:  # noqa: BLE001
        raise VaultError("2FA key is not valid base32") from e
    now = time.time() if at is None else at
    counter = int(now // step)
    digest = hmac.new(key, struct.pack(">Q", counter), "sha1").digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 10**digits
    return str(code).zfill(digits), step - int(now % step)
