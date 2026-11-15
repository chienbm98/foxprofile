"""Shared helpers for API routes (DRY)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException

from ..core.config import profile_data_dir
from ..services import proton_account
from .schemas.profiles import ProfileResponse

if TYPE_CHECKING:
    from ..interfaces import IBrowserLauncher, IProfileManager
    from ..models.profile import Profile


def require_profile(name: str, pm: IProfileManager) -> Profile:
    """The profile, or 404. Use the returned object rather than indexing
    pm.profiles again: a concurrent delete can remove it in between."""
    profile = pm.profiles.get(name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return profile


def build_profile_response(
    name: str,
    pm: IProfileManager,
    bl: IBrowserLauncher,
) -> ProfileResponse:
    """Build a ProfileResponse DTO for the given profile name."""
    return profile_response(require_profile(name, pm), bl)


def profile_response(
    profile: Profile,
    bl: IBrowserLauncher,
    account: proton_account.ProtonAccount | None = None,
) -> ProfileResponse:
    if account is None:
        account = proton_account.load(profile.name)
    return ProfileResponse(
        name=profile.name,
        proxy=profile.proxy,
        os_type=profile.os_type,
        timezone=profile.timezone,
        locale=profile.locale,
        engine=profile.engine,
        extension=profile.extension,
        proxy_mode=profile.proxy_mode,
        proton_user=account.username,
        has_proton_password=bool(account.password),
        proton_totp_set=bool(account.totp),
        proton_country=profile.proton_country,
        data_dir=profile_data_dir(profile.name),
        is_running=bl.is_running(profile.name),
    )
