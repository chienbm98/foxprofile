from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ...core.config import LAUNCH_WAIT_TIMEOUT
from ...core.logging import get_logger
from ...services.browser.launcher import ProfileBusyError
from ..dependencies import get_browser_launcher, get_event_bus, get_profile_manager
from ..helpers import require_profile
from ..schemas.browser import (
    BrowserStatusResponse,
    LaunchResponse,
    RunningBrowsersResponse,
)
from ..schemas.common import ErrorResponse, SuccessResponse

if TYPE_CHECKING:
    from ...core.events import EventBus
    from ...interfaces import IBrowserLauncher, IProfileManager

logger = get_logger("api.browser")

router = APIRouter(prefix="/browser", tags=["browser"])


def _api_log(msg: str) -> None:
    logger.info("[browser] %s", msg)


@router.get("", response_model=RunningBrowsersResponse)
def list_running(
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> RunningBrowsersResponse:
    names = sorted(bl.running_profile_names())
    return RunningBrowsersResponse(running=names, count=len(names))


@router.get(
    "/{name}/status",
    response_model=BrowserStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
def browser_status(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> BrowserStatusResponse:
    require_profile(name, pm)
    return BrowserStatusResponse(name=name, is_running=bl.is_running(name))


@router.post(
    "/{name}/launch",
    response_model=LaunchResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        502: {"model": LaunchResponse},
    },
)
def launch_browser(
    name: str,
    response: Response,
    wait: bool = Query(
        True,
        description="Wait until the browser is ready or has failed before replying",
    ),
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> LaunchResponse:
    require_profile(name, pm)
    if bl.is_running(name):
        raise HTTPException(status_code=409, detail="Browser already running")

    profile = pm.profiles[name]

    def _on_ready() -> None:
        bus.emit()

    def _on_stop() -> None:
        bus.emit()

    try:
        bl.start_thread(profile, _api_log, on_ready=_on_ready, on_stop=_on_stop)
    except ProfileBusyError as e:
        raise HTTPException(status_code=409, detail="Profile is busy") from e
    logger.info("API launched browser for: %s", name)
    bus.emit()

    if not wait:
        response.status_code = 202
        return LaunchResponse(success=True, message=f"Browser launching for '{name}'")

    ok, error = bl.wait_for_launch(name, LAUNCH_WAIT_TIMEOUT)
    if ok:
        return LaunchResponse(success=True, message=f"Browser started for '{name}'")
    if error == "timeout":
        response.status_code = 202
        return LaunchResponse(
            success=True,
            message=f"Browser for '{name}' is still starting",
        )
    response.status_code = 502
    return LaunchResponse(success=False, message=f"Launch failed: {error}")


@router.post(
    "/{name}/stop",
    response_model=SuccessResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def stop_browser(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> SuccessResponse:
    require_profile(name, pm)
    if not bl.is_running(name):
        raise HTTPException(status_code=409, detail="Browser is not running")

    bl.stop_profile(name)
    logger.info("API stopped browser for: %s", name)
    bus.emit()
    return SuccessResponse(message=f"Browser stopped for '{name}'")
