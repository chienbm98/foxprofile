"""Export profiles to one encrypted file and import them on another PC."""

from __future__ import annotations

import os
import platform
import tempfile
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from ...core.config import MACHINE_NAME
from ...services.profile import bundle
from ...services.vault import vault
from ..dependencies import get_browser_launcher, get_profile_manager

router = APIRouter(prefix="/transfer", tags=["transfer"])


class ExportBody(BaseModel):
    names: list[str] | None = None
    passphrase: str | None = None


def _passphrase(override: str | None) -> str:
    chosen = override or vault.get_passphrase()
    if not chosen:
        raise HTTPException(
            status_code=423,
            detail="Set the passphrase first (it protects the file and the stored passwords)",
        )
    return chosen


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
    stamp = time.strftime("%Y%m%d-%H%M")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=f"foxprofile-{stamp}.fpbundle",
        headers={"X-Exported": ",".join(result["profiles"]).encode("ascii", "ignore").decode()},
        background=BackgroundTask(os.unlink, path),
    )


@router.post("/import")
async def import_profiles(
    request: Request,
    overwrite: bool = False,
    pm=Depends(get_profile_manager),
    bl=Depends(get_browser_launcher),
) -> dict:
    """Body: the raw .fpbundle bytes. Header X-Bundle-Passphrase overrides the vault passphrase."""
    passphrase = _passphrase(request.headers.get("x-bundle-passphrase"))
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
        return bundle.import_bundle(pm, path, passphrase, overwrite, is_running=bl.is_running)
    except bundle.BundleError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        os.unlink(path)
