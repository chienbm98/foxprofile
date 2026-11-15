from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ...core.config import profile_data_dir
from ...core.errors import ProfileBusyError
from ...core.logging import get_logger
from ...models.profile import ENGINES, OS_TYPES, PROXY_MODES
from ...services import proton_account
from ...services.browser import chrome_prefetch, cookies, fingerprint
from ...services.browser.proton_countries import BY_CODE as PROTON_COUNTRIES
from ...services.proxy.geo_check import check_geo
from ...utils.validation import (
    validate_locale,
    validate_profile_name,
    validate_proxy_format,
    validate_timezone,
)
from ..dependencies import get_browser_launcher, get_event_bus, get_profile_manager
from ..helpers import build_profile_response, profile_response, require_profile
from ..schemas.common import ErrorResponse, SuccessResponse
from ..schemas.profiles import (
    CookieImportRequest,
    CookieImportResponse,
    DataDirResponse,
    ExportRequest,
    ExportResponse,
    FingerprintResponse,
    ImportRequest,
    ImportResponse,
    ProfileCreate,
    ProfileListResponse,
    ProfileResponse,
    ProfileUpdate,
)
from ..schemas.proxy import GeoCheckResponse

if TYPE_CHECKING:
    from ...core.events import EventBus
    from ...interfaces import IBrowserLauncher, IProfileManager

logger = get_logger("api.profiles")

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _require_os(os_type: str) -> None:
    if os_type not in OS_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"os_type must be one of: {', '.join(OS_TYPES)}",
        )


def _require_engine(engine: str) -> None:
    if engine not in ENGINES:
        raise HTTPException(
            status_code=400,
            detail=f"engine must be one of: {', '.join(ENGINES)}",
        )
    if engine == "chrome" and (reason := chrome_prefetch.unsupported_reason()):
        raise HTTPException(status_code=400, detail=f"Chrome engine unavailable here: {reason}")


def _require_geo(timezone: str | None, locale: str | None) -> None:
    for validate, value in ((validate_timezone, timezone), (validate_locale, locale)):
        valid, msg = validate(value or "")
        if not valid:
            raise HTTPException(status_code=400, detail=msg)


def _require_country(country: str | None) -> None:
    if country and country.upper() not in PROTON_COUNTRIES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown Proton country code: {country}",
        )


def _require_proxy_mode(mode: str) -> None:
    if mode not in PROXY_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"proxy_mode must be one of: {', '.join(PROXY_MODES)}",
        )


@router.get("", response_model=ProfileListResponse)
def list_profiles(
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> ProfileListResponse:
    # One read of the Proton accounts file for the whole list: the panel refreshes it every few seconds.
    accounts = proton_account.load_all()
    profiles = [
        profile_response(p, bl, accounts.get(p.name, proton_account.ProtonAccount()))
        for p in pm.list_profiles()
    ]
    return ProfileListResponse(profiles=profiles, total=len(profiles))


@router.post(
    "",
    response_model=ProfileResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_profile(
    body: ProfileCreate,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> ProfileResponse:
    valid, msg = validate_profile_name(body.name)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)
    _require_os(body.os_type)
    _require_engine(body.engine)
    _require_geo(body.timezone, body.locale)

    mode = body.proxy_mode or (
        "proton" if body.extension == "proton-vpn" else ("proxy" if body.proxy else "direct")
    )
    _require_proxy_mode(mode)
    if mode == "proxy":
        if not body.proxy:
            raise HTTPException(status_code=400, detail="proxy is required in proxy mode")
        valid, msg = validate_proxy_format(body.proxy)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)
    if mode == "proton":
        _require_country(body.proton_country)
        if not (body.proton_user or "").strip():
            raise HTTPException(status_code=400, detail="Proton username is required")
        if not (body.proton_password or ""):
            raise HTTPException(status_code=400, detail="Proton password is required")

    if not pm.add_profile(
        body.name,
        body.proxy or "",
        body.os_type,
        body.timezone or None,
        body.locale or None,
        body.engine,
        proxy_mode=mode,
        proton_user=body.proton_user or "",
        proton_password=body.proton_password or "",
        proton_totp=body.proton_totp or "",
        proton_country=body.proton_country or "",
    ):
        raise HTTPException(status_code=409, detail="Profile already exists")

    logger.info("API created profile: %s", body.name)
    if body.engine == "chrome":
        chrome_prefetch.start()
    bus.emit()
    return build_profile_response(body.name, pm, bl)


@router.get(
    "/{name}",
    response_model=ProfileResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_profile(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> ProfileResponse:
    require_profile(name, pm)
    return build_profile_response(name, pm, bl)


@router.patch(
    "/{name}",
    response_model=ProfileResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def update_profile(
    name: str,
    body: ProfileUpdate,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> ProfileResponse:
    profile = require_profile(name, pm)
    supplied = body.model_dump(exclude_unset=True)

    new_name = supplied.get("name", name)
    new_proxy = supplied.get("proxy", profile.proxy)
    new_os = supplied.get("os_type", profile.os_type)
    new_timezone = supplied.get("timezone", profile.timezone)
    new_locale = supplied.get("locale", profile.locale)

    if "proxy_mode" in supplied:
        mode = supplied["proxy_mode"] or "direct"
    elif "proxy" in supplied and profile.proxy_mode != "proton":
        mode = "proxy" if new_proxy else "direct"
    else:
        mode = profile.proxy_mode
    _require_proxy_mode(mode)

    if "name" in supplied:
        valid, msg = validate_profile_name(new_name)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)
        if new_name != name and bl.is_running(name):
            raise HTTPException(
                status_code=409,
                detail="Stop the browser before renaming",
            )

    if supplied.get("engine") not in (None, profile.engine):
        raise HTTPException(
            status_code=400,
            detail="A profile's engine cannot be changed; create a new profile instead",
        )
    if "os_type" in supplied:
        _require_os(new_os)
    _require_geo(supplied.get("timezone"), supplied.get("locale"))

    if mode == "proxy":
        if not new_proxy:
            raise HTTPException(status_code=400, detail="proxy is required in proxy mode")
        valid, msg = validate_proxy_format(new_proxy)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)
    new_proton_user = supplied.get("proton_user")
    new_proton_country = supplied.get("proton_country")
    if mode == "proton":
        _require_country(new_proton_country)
        account = proton_account.load(name)
        if new_proton_user is None and (
            supplied.get("proton_password") is not None or supplied.get("proton_totp") is not None
        ):
            new_proton_user = account.username
        user = (new_proton_user if new_proton_user is not None else account.username).strip()
        if not user:
            raise HTTPException(status_code=400, detail="Proton username is required")
        if not account.password and not supplied.get("proton_password"):
            raise HTTPException(status_code=400, detail="Proton password is required")

    if not pm.update_profile(
        name,
        new_name,
        new_proxy or "",
        new_os,
        new_timezone or None,
        new_locale or None,
        new_proxy_mode=mode,
        proton_user=new_proton_user,
        proton_password=supplied.get("proton_password"),
        proton_totp=supplied.get("proton_totp"),
        proton_country=new_proton_country,
    ):
        raise HTTPException(status_code=409, detail="Update failed (name conflict?)")

    logger.info("API updated profile: %s -> %s", name, new_name)
    bus.emit()
    return build_profile_response(new_name, pm, bl)


@router.delete(
    "/{name}",
    response_model=SuccessResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def delete_profile(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> SuccessResponse:
    require_profile(name, pm)
    if bl.is_running(name):
        raise HTTPException(
            status_code=409,
            detail="Stop the browser before deleting",
        )
    pm.delete_profile(name)
    logger.info("API deleted profile: %s", name)
    bus.emit()
    return SuccessResponse(message=f"Profile '{name}' deleted")


@router.get(
    "/{name}/data-dir",
    response_model=DataDirResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_data_dir(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
) -> DataDirResponse:
    require_profile(name, pm)
    data_dir = profile_data_dir(name)
    return DataDirResponse(
        name=name,
        data_dir=data_dir,
        exists=pathlib.Path(data_dir).exists(),
    )


@router.post(
    "/{name}/export",
    response_model=ExportResponse,
    responses={404: {"model": ErrorResponse}},
)
def export_profile(
    name: str,
    body: ExportRequest,
    pm: IProfileManager = Depends(get_profile_manager),
) -> ExportResponse:
    require_profile(name, pm)
    if not pathlib.Path(body.export_dir).is_dir():
        raise HTTPException(status_code=400, detail="export_dir is not a directory")

    success, result = pm.export_profile(name, body.export_dir, body.include_data)
    if success:
        logger.info("API exported profile: %s -> %s", name, result)
        return ExportResponse(success=True, zip_path=result)
    return ExportResponse(success=False, error=result)


@router.post(
    "/import",
    response_model=ImportResponse,
    responses={400: {"model": ErrorResponse}},
)
def import_profile(
    body: ImportRequest,
    pm: IProfileManager = Depends(get_profile_manager),
    bus: EventBus = Depends(get_event_bus),
) -> ImportResponse:
    if not pathlib.Path(body.zip_path).is_file():
        raise HTTPException(status_code=400, detail="zip_path is not a file")

    success, result = pm.import_profile(body.zip_path, body.overwrite)
    if success:
        logger.info("API imported profile: %s", result)
        bus.emit()
        return ImportResponse(success=True, profile_name=result)
    return ImportResponse(success=False, error=result)


def _require_stopped(name: str, bl: IBrowserLauncher, action: str) -> None:
    if bl.is_running(name):
        raise HTTPException(status_code=409, detail=f"Stop the browser before {action}")


_BUSY_DETAIL = "Profile is running or busy with another operation"


@router.get(
    "/{name}/cookies",
    response_class=PlainTextResponse,
    responses={
        200: {"content": {"text/plain": {}, "application/json": {}}},
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def export_cookies(
    name: str,
    format: str = Query("json", pattern="^(json|netscape)$"),
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> PlainTextResponse:
    """Export cookies as Cookie-Editor JSON or Netscape cookies.txt."""
    profile = require_profile(name, pm)
    _require_stopped(name, bl, "exporting cookies")
    try:
        with bl.exclusive(name):
            text, count = cookies.export_cookies(name, profile.os_type, format, profile.engine)
    except ProfileBusyError as e:
        raise HTTPException(status_code=409, detail=_BUSY_DETAIL) from e
    except cookies.CookieError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    media = "application/json" if format == "json" else "text/plain"
    return PlainTextResponse(text, media_type=media, headers={"X-Cookie-Count": str(count)})


@router.post(
    "/{name}/cookies",
    response_model=CookieImportResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def import_cookies(
    name: str,
    body: CookieImportRequest,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> CookieImportResponse:
    """Import cookies from JSON or Netscape text into a stopped profile."""
    profile = require_profile(name, pm)
    _require_stopped(name, bl, "importing cookies")
    try:
        with bl.exclusive(name):
            count = cookies.import_cookies(name, profile.os_type, body.content, profile.engine)
    except ProfileBusyError as e:
        raise HTTPException(status_code=409, detail=_BUSY_DETAIL) from e
    except cookies.CookieError as e:
        return CookieImportResponse(success=False, error=str(e))
    logger.info("API imported %d cookies into %s", count, name)
    return CookieImportResponse(success=True, imported=count)


@router.get(
    "/{name}/fingerprint",
    response_model=FingerprintResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_fingerprint(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
) -> FingerprintResponse:
    """Show the fingerprint the profile presents on every launch."""
    require_profile(name, pm)
    info = fingerprint.summary(profile_data_dir(name))
    if info is None:
        return FingerprintResponse(name=name, exists=False)
    return FingerprintResponse(name=name, exists=True, **info)


@router.delete(
    "/{name}/fingerprint",
    response_model=SuccessResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def reset_fingerprint(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> SuccessResponse:
    """Discard the saved fingerprint; the next launch generates a new device."""
    require_profile(name, pm)
    _require_stopped(name, bl, "resetting the fingerprint")
    try:
        with bl.exclusive(name):
            removed = fingerprint.reset(profile_data_dir(name))
    except ProfileBusyError as e:
        raise HTTPException(status_code=409, detail=_BUSY_DETAIL) from e
    logger.info("API reset fingerprint for %s (existed=%s)", name, removed)
    return SuccessResponse(message=f"Fingerprint reset for '{name}'")


@router.get(
    "/{name}/ip-check",
    response_model=GeoCheckResponse,
    responses={404: {"model": ErrorResponse}},
)
def check_profile_ip(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
) -> GeoCheckResponse:
    """Where GeoIP sources place the profile's exit IP vs. the timezone/locale it presents.

    Goes out through the profile's proxy to Cloudflare, ipinfo and ip-api (~10s).
    """
    profile = require_profile(name, pm)
    data_dir = profile_data_dir(profile.name)
    return GeoCheckResponse.from_result(
        check_geo(profile.proxy, profile.timezone, profile.locale, data_dir)
    )
