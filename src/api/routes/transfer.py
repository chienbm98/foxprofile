"""Export profiles to one encrypted file and import them on another PC.

For PCs that never share a network, or run from a USB stick: download the file, or save it
straight onto a USB stick / a folder, and import it from there on the other PC.
"""

from __future__ import annotations

import os
import pathlib
import platform
import tempfile
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from ...core.config import MACHINE_NAME
from ...services.profile import bundle
from ...services.sync.backends import find_usb_folder
from ...services.vault import vault
from ..dependencies import get_browser_launcher, get_profile_manager

router = APIRouter(prefix="/transfer", tags=["transfer"])

USB_FOLDER = "foxprofile-sync"
EXPORT_DIR = "exports"


class ExportBody(BaseModel):
    names: list[str] | None = None
    passphrase: str | None = None


class SaveBody(ExportBody):
    target: str = "usb"  # "usb", "local" (the exports folder here) or a folder path


class PathBody(BaseModel):
    path: str
    only: list[str] | None = None
    overwrite: bool = False


def _passphrase(override: str | None) -> str:
    chosen = override or vault.get_passphrase()
    if not chosen:
        raise HTTPException(
            status_code=423,
            detail="Set the passphrase first (it protects the file and the stored passwords)",
        )
    return chosen


def _file_name(names: list[str] | None) -> str:
    who = names[0] if names and len(names) == 1 else (MACHINE_NAME or platform.node() or "all")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in who)
    return f"foxprofile-{safe}-{time.strftime('%Y%m%d-%H%M%S')}.fpbundle"


def _usb_bundle_dir(create: bool) -> pathlib.Path | None:
    folder = find_usb_folder(USB_FOLDER, create=create)
    return folder / "bundles" if folder else None


def _known_dirs() -> list[tuple[str, pathlib.Path]]:
    dirs: list[tuple[str, pathlib.Path]] = []
    usb = _usb_bundle_dir(create=False)
    if usb:
        dirs.append(("usb", usb))
    dirs.append(("local", pathlib.Path(EXPORT_DIR)))
    return dirs


def _bundle_path(raw: str) -> str:
    path = pathlib.Path(raw)
    if path.suffix.lower() != ".fpbundle" or not path.is_file():
        raise HTTPException(status_code=400, detail="Choose an existing .fpbundle file")
    return str(path)


@router.post("/export")
def export_profiles(
    body: ExportBody,
    pm=Depends(get_profile_manager),
    bl=Depends(get_browser_launcher),
) -> FileResponse:
    """Download the chosen profiles (all when none are named) as an encrypted .fpbundle."""
    fd, path = tempfile.mkstemp(suffix=".fpbundle")
    os.close(fd)
    try:
        result = bundle.export_bundle(
            pm,
            body.names,
            _passphrase(body.passphrase),
            path,
            is_running=bl.is_running,
            machine=MACHINE_NAME or platform.node(),
        )
    except bundle.BundleError as e:
        os.unlink(path)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        os.unlink(path)
        raise
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=_file_name(body.names),
        headers={"X-Exported": ",".join(result["profiles"]).encode("ascii", "ignore").decode()},
        background=BackgroundTask(os.unlink, path),
    )


@router.post("/export-to-folder")
def export_to_folder(
    body: SaveBody,
    pm=Depends(get_profile_manager),
    bl=Depends(get_browser_launcher),
) -> dict[str, Any]:
    """Write the .fpbundle straight onto a USB stick, the local exports folder, or any folder."""
    if body.target == "usb":
        folder = _usb_bundle_dir(create=True)
        if folder is None:
            raise HTTPException(
                status_code=400,
                detail="No USB stick found. Plug one in (a folder 'foxprofile-sync' is created on it).",
            )
    elif body.target == "local":
        folder = pathlib.Path(EXPORT_DIR)
    else:
        folder = pathlib.Path(body.target)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / _file_name(body.names)
        result = bundle.export_bundle(
            pm,
            body.names,
            _passphrase(body.passphrase),
            str(dest),
            is_running=bl.is_running,
            machine=MACHINE_NAME or platform.node(),
        )
    except bundle.BundleError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Could not write there: {e}") from e
    return {**result, "bytes": dest.stat().st_size, "path": str(dest.resolve())}


@router.get("/bundles")
def list_bundles() -> dict[str, Any]:
    """Bundles already on a USB stick or in the local exports folder, newest first."""
    found: list[dict[str, Any]] = []
    for where, folder in _known_dirs():
        if folder.is_dir():
            for f in folder.glob("*.fpbundle"):
                st = f.stat()
                found.append(
                    {
                        "where": where,
                        "name": f.name,
                        "path": str(f.resolve()),
                        "bytes": st.st_size,
                        "modified": st.st_mtime,
                    }
                )
    found.sort(key=lambda x: x["modified"], reverse=True)
    return {"bundles": found}


async def _save_upload(request: Request) -> str:
    fd, path = tempfile.mkstemp(suffix=".fpbundle")
    try:
        with os.fdopen(fd, "wb") as out:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > bundle.MAX_BUNDLE_BYTES:
                    raise HTTPException(status_code=413, detail="File too large")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="No file received")
    except BaseException:
        os.unlink(path)
        raise
    return path


def _with_existing(info: dict[str, Any], pm) -> dict[str, Any]:
    for p in info["profiles"]:
        p["exists_here"] = p["name"] in pm.profiles
    return info


@router.post("/inspect")
async def inspect_upload(request: Request, pm=Depends(get_profile_manager)) -> dict:
    """Body: the raw .fpbundle bytes. Lists what is inside without importing."""
    passphrase = _passphrase(request.headers.get("x-bundle-passphrase"))
    path = await _save_upload(request)
    try:
        return _with_existing(bundle.inspect_bundle(path, passphrase), pm)
    except bundle.BundleError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        os.unlink(path)


@router.post("/inspect-path")
def inspect_path(body: PathBody, pm=Depends(get_profile_manager)) -> dict:
    try:
        info = bundle.inspect_bundle(_bundle_path(body.path), _passphrase(None))
    except bundle.BundleError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _with_existing(info, pm)


@router.post("/import")
async def import_profiles(
    request: Request,
    overwrite: bool = False,
    only: list[str] | None = Query(None, description="Profile names to import (default: all)"),
    pm=Depends(get_profile_manager),
    bl=Depends(get_browser_launcher),
) -> dict:
    """Body: the raw .fpbundle bytes. Header X-Bundle-Passphrase overrides the vault passphrase."""
    passphrase = _passphrase(request.headers.get("x-bundle-passphrase"))
    path = await _save_upload(request)
    try:
        return bundle.import_bundle(
            pm, path, passphrase, overwrite, is_running=bl.is_running, only=only
        )
    except bundle.BundleError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        os.unlink(path)


@router.post("/import-path")
def import_from_path(
    body: PathBody,
    pm=Depends(get_profile_manager),
    bl=Depends(get_browser_launcher),
) -> dict:
    """Import a .fpbundle that is already on this PC (a USB stick, the exports folder...)."""
    try:
        return bundle.import_bundle(
            pm,
            _bundle_path(body.path),
            _passphrase(None),
            body.overwrite,
            is_running=bl.is_running,
            only=body.only,
        )
    except bundle.BundleError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
