"""Sync profiles (with their logins) through an encrypted shared store."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from ...services.sync.backends import SyncError
from ...services.sync.service import SyncConflict, SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


def get_sync(request: Request) -> SyncService:
    svc = request.app.state.container.sync_service
    if not svc.configured:
        raise HTTPException(
            status_code=400,
            detail="Sync is not configured: set FOXPROFILE_SYNC_URL and FOXPROFILE_SYNC_PASSPHRASE",
        )
    return svc


def _call(fn, *args) -> Any:
    try:
        return fn(*args)
    except SyncConflict as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("")
def status(svc: SyncService = Depends(get_sync)) -> dict:
    profiles = _call(svc.status)
    return {"store": svc.store_label, "profiles": profiles}


@router.post("/push")
def push_all(force: bool = False, svc: SyncService = Depends(get_sync)) -> dict:
    return _call(svc.push_all, force)


@router.post("/pull")
def pull_all(force: bool = False, svc: SyncService = Depends(get_sync)) -> dict:
    return _call(svc.pull_all, force)


@router.post("/{name}/push")
def push(name: str, force: bool = False, svc: SyncService = Depends(get_sync)) -> dict:
    return _call(svc.push, name, force)


@router.post("/{name}/pull")
def pull(
    request: Request,
    name: str,
    force: bool = False,
    check: bool = False,
    svc: SyncService = Depends(get_sync),
) -> dict:
    """Pull a profile; with check=true also verify in the background that its Gmail
    session survived the move (opens the profile briefly)."""
    result = _call(svc.pull, name, force)
    if check and not result.get("skipped"):
        request.app.state.container.automation.check_sessions([name])
    return result


@router.get("/log")
def sync_log(
    limit: int = 100, profile: str | None = None, svc: SyncService = Depends(get_sync)
) -> dict:
    """Newest first: every push, pull and auto-sync decision with its timings and sizes."""
    return {
        "path": str(svc.log.path),
        "text_path": str(svc.text_log_path.resolve()),
        "events": svc.log.tail(max(1, min(limit, 1000)), profile),
    }


@router.post("/log/save")
def save_log(svc: SyncService = Depends(get_sync)) -> dict:
    """Write the log to a file in the app's top folder; returns its path to copy or send."""
    path = svc.save_snapshot()
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "folder": str(path.resolve().parent),
        "bytes": path.stat().st_size,
        "auto_path": str(svc.text_log_path.resolve()),
    }


@router.get("/log/file")
def log_file(svc: SyncService = Depends(get_sync)) -> FileResponse:
    """Download a fresh snapshot of the log as a text file."""
    path = svc.save_snapshot()
    return FileResponse(path, media_type="text/plain", filename=path.name)


@router.post("/log/open-folder")
def open_log_folder(request: Request, svc: SyncService = Depends(get_sync)) -> dict:
    """Show the folder in Explorer. Only for a browser on the same PC as the server."""
    if (request.client.host if request.client else "") not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=403, detail="Only possible from the PC that runs FoxProfile"
        )
    import subprocess
    import sys

    folder = str(__import__("pathlib").Path(svc.app_root).resolve())
    if sys.platform == "win32":
        subprocess.Popen(["explorer", folder])  # noqa: S603, S607
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])  # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", folder])  # noqa: S603, S607
    return {"folder": folder}


@router.put("/{name}/auto")
def set_auto(name: str, enabled: bool = True, svc: SyncService = Depends(get_sync)) -> dict:
    """Per-profile: pull a newer copy before launch and push when the profile stops."""
    return {"name": name, "auto": svc.set_auto(name, enabled)}


@router.delete("/{name}")
def remove_remote(name: str, svc: SyncService = Depends(get_sync)) -> dict:
    """Remove a profile from the store only; local data is untouched."""
    _call(svc.remove_remote, name)
    return {"success": True}
