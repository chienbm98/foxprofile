"""Encrypted account secrets, the vault passphrase and automatic re-login.

Secrets are only ever returned by the explicit reveal calls below, which the web panel
uses for "copy password" and the live 2FA code. They are deliberately not exposed as MCP
tools, so an AI agent browsing untrusted pages cannot be talked into reading them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...services.automation.engine import Automation, AutomationError
from ...services.vault import vault
from ...services.vault.accounts import AccountVault
from ..dependencies import get_profile_manager
from ..helpers import require_profile

router = APIRouter(tags=["accounts"])


def get_vault(request: Request) -> AccountVault:
    return request.app.state.container.account_vault


def _guard(fn, *args):
    try:
        return fn(*args)
    except vault.VaultLocked as e:
        raise HTTPException(status_code=423, detail=str(e)) from e
    except vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class SecretsBody(BaseModel):
    """Only the fields sent are changed; null or "" removes a stored one."""

    password: str | None = Field(None, max_length=512)
    totp_secret: str | None = Field(None, max_length=256, description="Base32 2FA key")
    backup_codes: str | None = Field(None, max_length=4000)
    recovery: str | None = Field(None, max_length=500)
    hint: str | None = Field(None, max_length=500)


@router.put("/profiles/{name}/secrets")
def set_secrets(
    name: str,
    body: SecretsBody,
    pm=Depends(get_profile_manager),
    av: AccountVault = Depends(get_vault),
) -> dict:
    require_profile(name, pm)
    return _guard(av.set_secrets, name, body.model_dump(exclude_unset=True))


@router.get("/profiles/{name}/secrets/{field}")
def reveal_secret(
    name: str,
    field: str,
    pm=Depends(get_profile_manager),
    av: AccountVault = Depends(get_vault),
) -> dict:
    require_profile(name, pm)
    return {"field": field, "value": _guard(av.reveal, name, field)}


@router.get("/profiles/{name}/totp")
def current_totp(
    name: str,
    pm=Depends(get_profile_manager),
    av: AccountVault = Depends(get_vault),
) -> dict:
    """The current 6-digit 2FA code and the seconds it stays valid."""
    require_profile(name, pm)
    return _guard(av.totp_code, name)


class PassphraseBody(BaseModel):
    passphrase: str = Field(min_length=1, max_length=512)
    persist: bool = Field(True, description="Keep it in the OS credential store")


@router.get("/vault")
def vault_status() -> dict:
    return {"unlocked": vault.is_unlocked()}


@router.post("/vault/passphrase")
def vault_set_passphrase(body: PassphraseBody) -> dict:
    where = _guard(vault.set_passphrase, body.passphrase, body.persist)
    return {"unlocked": True, "kept_in": where}


@router.delete("/vault/passphrase")
def vault_clear_passphrase() -> dict:
    vault.clear_passphrase()
    return {"unlocked": vault.is_unlocked()}


@router.post("/automation/relogin/{name}")
def relogin(name: str, request: Request, pm=Depends(get_profile_manager)) -> dict:
    """Sign the profile back in to Gmail in the background (launches it if closed). The
    outcome lands on the profile (session_state) and in the activity log."""
    require_profile(name, pm)
    auto: Automation = request.app.state.container.automation
    try:
        auto.relogin_async(name)
    except AutomationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"started": name}
