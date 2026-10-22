"""Read and write a profile's encrypted account secrets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import vault

if TYPE_CHECKING:
    from ...interfaces import IProfileManager


class AccountVault:
    def __init__(self, pm: IProfileManager) -> None:
        self.pm = pm

    def _profile(self, name: str):
        profile = self.pm.profiles.get(name)
        if profile is None:
            raise vault.VaultError(f"profile '{name}' not found")
        return profile

    def flags(self, name: str) -> dict[str, bool]:
        """Which secrets are stored, without decrypting anything."""
        secrets = self._profile(name).secrets
        return {f"has_{field}": field in secrets for field in vault.SECRET_FIELDS}

    def set_secrets(self, name: str, values: dict[str, str | None]) -> dict[str, bool]:
        """Store the given fields encrypted; None or an empty string removes one."""
        unknown = set(values) - set(vault.SECRET_FIELDS)
        if unknown:
            raise vault.VaultError(f"unknown secret fields: {', '.join(sorted(unknown))}")
        current = dict(self._profile(name).secrets)
        for field, value in values.items():
            if value:
                if field == "totp_secret":
                    vault.totp(value)  # reject a key that is not valid base32
                current[field] = vault.encrypt(value)
            else:
                current.pop(field, None)
        self.pm.update_meta(name, secrets=current)
        return self.flags(name)

    def reveal(self, name: str, field: str) -> str:
        if field not in vault.SECRET_FIELDS:
            raise vault.VaultError(f"unknown secret field: {field}")
        token = self._profile(name).secrets.get(field)
        if token is None:
            raise vault.VaultError(f"no {field} stored for '{name}'")
        return vault.decrypt(token)

    def totp_code(self, name: str) -> dict[str, int | str]:
        code, remaining = vault.totp(self.reveal(name, "totp_secret"))
        return {"code": code, "remaining": remaining}
