"""Per-profile Proton accounts used by the extension's automatic sign-in.

Entered in the profile dialog and stored next to `profiles.json`:

    proton_accounts.json   one entry per profile: username, password, TOTP secret
    proton_accounts.key    random Fernet key, mode 0600

The password and the TOTP secret are encrypted with that key. Both files are
gitignored and are not part of a profile export, and secrets never reach
`profiles.json`, logs or the command line. The key file protects against
accidental sharing, not against someone who can read the whole data directory.

Neither file is ever replaced silently. If the key or the accounts file cannot
be read, saving raises ProtonStoreError: overwriting it would make every saved
secret unreadable for good.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from ..core import config
from ..core.errors import ProtonStoreError
from ..core.logging import get_logger
from ..utils.files import write_private

logger = get_logger("proton.account")


@dataclass(frozen=True)
class ProtonAccount:
    username: str = ""
    password: str = ""
    totp: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.username and self.password)

    def public(self) -> dict:
        """What the UI and API may see: never the password or the TOTP secret."""
        return {
            "username": self.username,
            "has_password": bool(self.password),
            "totp_set": bool(self.totp),
        }


def _path() -> Path:
    return Path(config.PROTON_ACCOUNTS_FILE)


def _key_path() -> Path:
    return Path(config.PROTON_ACCOUNTS_KEY_FILE)


# --- key -------------------------------------------------------------------------


def _read_key() -> bytes | None:
    """The stored key, or None when there is no key file yet."""
    path = _key_path()
    try:
        raw = path.read_bytes().strip()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ProtonStoreError(f"cannot read {path.name}: {e.strerror or e}") from e
    try:
        Fernet(raw)
    except ValueError as e:
        raise ProtonStoreError(f"{path.name} does not hold a valid key") from e
    return raw


def _key_for_write() -> bytes:
    """The key to encrypt with. Created on first use; an existing key is never replaced."""
    key = _read_key()
    if key is not None:
        return key
    path = _key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # O_EXCL: if another process created the key a moment ago, use that one.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = _read_key()
        if key is None:
            raise ProtonStoreError(f"{path.name} vanished while it was being created") from None
        return key
    fresh = Fernet.generate_key()
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(fresh)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        with contextlib.suppress(OSError):
            path.unlink()
        raise
    return fresh


def _usable_key() -> bytes | None:
    """The key for reading secrets; an unreadable key is logged and treated as absent."""
    try:
        return _read_key()
    except ProtonStoreError as e:
        logger.warning("%s", e)
        return None


def _encrypt(value: str) -> str:
    return Fernet(_key_for_write()).encrypt(value.encode()).decode()


def _decrypt(token: str, key: bytes | None, profile: str, what: str) -> str:
    if not token:
        return ""
    if key is None:
        logger.warning("The saved %s of profile %s cannot be read: no usable key", what, profile)
        return ""
    try:
        return Fernet(key).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        logger.warning("Could not decrypt the saved %s of profile %s", what, profile)
        return ""


# --- accounts file -----------------------------------------------------------------


def _load_entries() -> dict[str, Any]:
    path = _path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise ProtonStoreError(f"cannot read {path.name}: {e.strerror or e}") from e
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ProtonStoreError(f"{path.name} is not valid JSON; move it aside to start over") from e
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, dict):
        raise ProtonStoreError(f"{path.name} has an unexpected layout")
    return profiles


def _store(profiles: dict[str, Any]) -> None:
    if not profiles:
        clear_all()
        return
    payload = {"profiles": profiles}
    write_private(_path(), json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))


def _account(entry: dict[str, Any], key: bytes | None, profile: str) -> ProtonAccount:
    totp = _decrypt(str(entry.get("totp_token") or ""), key, profile, "TOTP secret")
    if not totp:
        # Entries written before the TOTP secret was encrypted keep it in plain text
        # until their next save, which encrypts it.
        totp = str(entry.get("totp") or "")
    return ProtonAccount(
        username=str(entry.get("username") or ""),
        password=_decrypt(str(entry.get("password") or ""), key, profile, "password"),
        totp=totp,
    )


def load(profile: str) -> ProtonAccount:
    try:
        entries = _load_entries()
    except ProtonStoreError as e:
        logger.warning("%s", e)
        return ProtonAccount()
    entry = entries.get(profile)
    if not isinstance(entry, dict):
        return ProtonAccount()
    return _account(entry, _usable_key(), profile)


def load_all() -> dict[str, ProtonAccount]:
    """Every saved account, reading the files once (the profile list calls this on each refresh)."""
    try:
        entries = _load_entries()
    except ProtonStoreError as e:
        logger.warning("%s", e)
        return {}
    key = _usable_key() if entries else None
    return {
        name: _account(entry, key, name)
        for name, entry in entries.items()
        if isinstance(entry, dict)
    }


def save(
    profile: str,
    username: str,
    password: str | None = None,
    totp: str | None = None,
) -> ProtonAccount:
    """Store one profile's account. `None` keeps what is saved; "" removes that secret."""
    username = username.strip()
    profiles = _load_entries()  # ProtonStoreError propagates: never overwrite what we cannot read
    if not username:
        profiles.pop(profile, None)
        _store(profiles)
        return ProtonAccount()

    old = profiles.get(profile)
    old = old if isinstance(old, dict) else {}
    current = _account(old, _usable_key(), profile) if old else ProtonAccount()

    entry: dict[str, Any] = {"username": username}
    # Ciphertext that is kept is copied as it is, so a password saved under a key that
    # cannot be read today survives a username change.
    if password is None:
        if old.get("password"):
            entry["password"] = old["password"]
    elif password:
        entry["password"] = _encrypt(password)

    if totp is None:
        if old.get("totp_token"):
            entry["totp_token"] = old["totp_token"]
        elif str(old.get("totp") or "").strip():
            entry["totp_token"] = _encrypt(str(old["totp"]).strip())
    elif totp.strip():
        entry["totp_token"] = _encrypt(totp.strip())

    profiles[profile] = entry
    _store(profiles)
    logger.info("Saved the Proton account for profile %s", profile)
    return ProtonAccount(
        username=username,
        password=current.password if password is None else password,
        totp=current.totp if totp is None else totp.strip(),
    )


def clear(profile: str) -> None:
    """Remove one profile's account. An unreadable file is left untouched."""
    try:
        profiles = _load_entries()
    except ProtonStoreError as e:
        logger.warning("The Proton account of %s was not cleared: %s", profile, e)
        return
    if profile in profiles:
        profiles.pop(profile)
        _store(profiles)
        logger.info("Cleared the Proton account for profile %s", profile)


def rename(old: str, new: str) -> None:
    profiles = _load_entries()
    if old in profiles:
        profiles[new] = profiles.pop(old)
        _store(profiles)


def clear_all() -> None:
    for path in (_path(), _key_path()):
        with contextlib.suppress(OSError):
            path.unlink()
    logger.info("Cleared all Proton accounts")
