"""Control the pages of a running profile: navigate, read, click, type, capture."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ...services.browser.launcher import BrowserControlError
from ..dependencies import get_browser_launcher, get_profile_manager
from ..helpers import require_profile
from ..schemas.page import (
    ClickAtRequest,
    ClickRequest,
    EvaluateRequest,
    KeyboardTypeRequest,
    NavigateRequest,
    PressRequest,
    ScrollRequest,
    TabNewRequest,
    TypeRequest,
    UploadRequest,
    WaitRequest,
    WaitTextRequest,
    WaitUrlRequest,
)

if TYPE_CHECKING:
    from ...interfaces import IBrowserLauncher, IProfileManager

router = APIRouter(prefix="/browser/{name}/page", tags=["page"])


def _run(
    name: str,
    pm: IProfileManager,
    bl: IBrowserLauncher,
    action: str,
    params: dict[str, Any] | None = None,
) -> Any:
    require_profile(name, pm)
    try:
        return bl.control(name, action, params or {})
    except BrowserControlError as e:
        raise HTTPException(status_code=e.status, detail=str(e)) from e


_PM = Depends(get_profile_manager)
_BL = Depends(get_browser_launcher)


@router.post("/navigate")
def navigate(name: str, body: NavigateRequest, pm=_PM, bl=_BL) -> dict:
    """Open a URL (http, https or about:) in the active tab."""
    return _run(name, pm, bl, "navigate", body.model_dump())


@router.post("/back")
def back(name: str, pm=_PM, bl=_BL) -> dict:
    return _run(name, pm, bl, "back")


@router.get("/snapshot")
def snapshot(
    name: str,
    max_chars: int = Query(40_000, ge=500, le=200_000),
    interactive_only: bool = False,
    pm=_PM,
    bl=_BL,
) -> dict:
    """Accessibility tree of the active tab, the best view for choosing selectors.

    `interactive_only=true` keeps only buttons, links, inputs and similar controls.
    """
    return _run(
        name, pm, bl, "snapshot", {"max_chars": max_chars, "interactive_only": interactive_only}
    )


@router.get("/text")
def text(
    name: str,
    selector: str = "body",
    max_chars: int = Query(40_000, ge=500, le=200_000),
    pm=_PM,
    bl=_BL,
) -> dict:
    return _run(name, pm, bl, "text", {"selector": selector, "max_chars": max_chars})


@router.post("/click")
def click(name: str, body: ClickRequest, pm=_PM, bl=_BL) -> dict:
    """Click the first element matching a Playwright selector (CSS, text=, role=)."""
    return _run(name, pm, bl, "click", body.model_dump())


@router.post("/type")
def type_text(name: str, body: TypeRequest, pm=_PM, bl=_BL) -> dict:
    return _run(name, pm, bl, "type", body.model_dump())


@router.post("/press")
def press(name: str, body: PressRequest, pm=_PM, bl=_BL) -> dict:
    return _run(name, pm, bl, "press", body.model_dump())


@router.post("/click-at")
def click_at(name: str, body: ClickAtRequest, pm=_PM, bl=_BL) -> dict:
    """Click viewport coordinates (as on a non-full-page screenshot)."""
    return _run(name, pm, bl, "click_at", body.model_dump())


@router.post("/keyboard")
def keyboard_type(name: str, body: KeyboardTypeRequest, pm=_PM, bl=_BL) -> dict:
    """Type text into the focused element."""
    return _run(name, pm, bl, "keyboard_type", body.model_dump())


@router.post("/wait")
def wait_for(name: str, body: WaitRequest, pm=_PM, bl=_BL) -> dict:
    return _run(name, pm, bl, "wait_for", body.model_dump())


@router.post("/wait-url")
def wait_for_url(name: str, body: WaitUrlRequest, pm=_PM, bl=_BL) -> dict:
    """Wait until the active tab's URL contains `pattern`."""
    return _run(name, pm, bl, "wait_for_url", body.model_dump())


@router.post("/wait-text")
def wait_for_text(name: str, body: WaitTextRequest, pm=_PM, bl=_BL) -> dict:
    """Wait until `text` is visible on the page."""
    return _run(name, pm, bl, "wait_for_text", body.model_dump())


@router.post("/scroll")
def scroll(name: str, body: ScrollRequest, pm=_PM, bl=_BL) -> dict:
    return _run(name, pm, bl, "scroll", body.model_dump())


@router.post("/upload")
def upload(name: str, body: UploadRequest, pm=_PM, bl=_BL) -> dict:
    """Set files on a file input; files must be inside the upload directory."""
    return _run(name, pm, bl, "upload", body.model_dump())


@router.get("/screenshot", responses={200: {"content": {"image/png": {}}}})
def screenshot(
    name: str,
    full_page: bool = False,
    format: str = Query("png", pattern="^(png|json)$"),
    pm=_PM,
    bl=_BL,
) -> Any:
    """PNG of the active tab; `format=json` returns it base64-encoded with url and title."""
    result = _run(name, pm, bl, "screenshot", {"full_page": full_page})
    if format == "json":
        return result
    return Response(
        base64.b64decode(result["png_base64"]),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/evaluate")
def evaluate(name: str, body: EvaluateRequest, pm=_PM, bl=_BL) -> dict:
    """Run JavaScript in the active tab and return its JSON-serialisable result."""
    return _run(name, pm, bl, "evaluate", body.model_dump())


@router.get("/tabs")
def tabs(name: str, pm=_PM, bl=_BL) -> dict:
    return _run(name, pm, bl, "tabs")


@router.post("/tabs")
def tab_new(name: str, body: TabNewRequest, pm=_PM, bl=_BL) -> dict:
    return _run(name, pm, bl, "tab_new", body.model_dump())


@router.post("/tabs/{index}/select")
def tab_select(name: str, index: int, pm=_PM, bl=_BL) -> dict:
    return _run(name, pm, bl, "tab_select", {"index": index})


@router.delete("/tabs/{index}")
def tab_close(name: str, index: int, pm=_PM, bl=_BL) -> dict:
    return _run(name, pm, bl, "tab_close", {"index": index})
