"""Move several profiles between PCs as one encrypted file (`.fpbundle`).

The file is a ZIP (a manifest plus one slim profile archive per profile) encrypted with the
vault passphrase, so it is safe to carry on a USB stick or send over the LAN. Passwords and
2FA keys inside a profile stay encrypted under the vault passphrase as well, so the receiving
PC needs the same passphrase for the whole file and for those secrets.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import tempfile
import time
import zipfile
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ...core.config import DATA_DIR
from ..sync.crypto import DecryptError, decrypt_stream, encrypt_stream
from .transfer import export_to_zip

if TYPE_CHECKING:
    from ...interfaces import IProfileManager

BUNDLE_VERSION = 1
_ENTRY = re.compile(r"^[^/\\]{1,80}\.zip$")
MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024


class BundleError(Exception):
    pass


def export_bundle(
    pm: IProfileManager,
    names: list[str] | None,
    passphrase: str,
    dest_path: str,
    is_running: Callable[[str], bool] = lambda n: False,
    machine: str = "",
    data_dir: str | None = None,
) -> dict[str, Any]:
    """Write the chosen profiles (all when `names` is empty) to `dest_path`."""
    if not passphrase:
        raise BundleError("A passphrase is required to protect the file")
    chosen = list(names) if names else sorted(pm.profiles)
    unknown = [n for n in chosen if n not in pm.profiles]
    if unknown:
        raise BundleError(f"unknown profiles: {', '.join(unknown)}")
    skipped: dict[str, str] = {}
    included: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        plain = os.path.join(tmp, "bundle.zip")
        with zipfile.ZipFile(plain, "w", zipfile.ZIP_STORED) as bundle:
            for name in chosen:
                if is_running(name):
                    skipped[name] = "running: stop it first so its files are consistent"
                    continue
                ok, result = export_to_zip(
                    pm.profiles[name],
                    os.path.join(data_dir or DATA_DIR, name),
                    tmp,
                    True,
                    slim=True,
                    filename=f"{len(included)}.zip",
                )
                if not ok:
                    skipped[name] = f"export failed: {result}"
                    continue
                bundle.write(result, f"{name}.zip")
                included.append(name)
            if not included:
                raise BundleError(
                    "Nothing to export: "
                    + ("; ".join(f"{k}: {v}" for k, v in skipped.items()) or "no profiles")
                )
            manifest = {
                "version": BUNDLE_VERSION,
                "created": time.time(),
                "machine": machine,
                "profiles": included,
            }
            bundle.writestr("manifest.json", json.dumps(manifest))
        with open(plain, "rb") as src, open(dest_path, "wb") as dst:
            encrypt_stream(src, dst, passphrase)
    return {"profiles": included, "skipped": skipped, "path": dest_path}


def import_bundle(
    pm: IProfileManager,
    path: str,
    passphrase: str,
    overwrite: bool = False,
    is_running: Callable[[str], bool] = lambda n: False,
    data_dir: str | None = None,
) -> dict[str, Any]:
    if not passphrase:
        raise BundleError("A passphrase is required to open the file")
    if os.path.getsize(path) > MAX_BUNDLE_BYTES:
        raise BundleError("File is too large to be a profile bundle")
    imported: list[str] = []
    skipped: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        plain = os.path.join(tmp, "bundle.zip")
        try:
            with open(path, "rb") as src, open(plain, "wb") as dst:
                decrypt_stream(src, dst, passphrase)
        except DecryptError as e:
            raise BundleError(str(e)) from e
        try:
            bundle = zipfile.ZipFile(plain)
        except zipfile.BadZipFile as e:
            raise BundleError("The file is not a FoxProfile bundle") from e
        with bundle:
            try:
                manifest = json.loads(bundle.read("manifest.json"))
            except (KeyError, ValueError) as e:
                raise BundleError("The file is not a FoxProfile bundle (no manifest)") from e
            if manifest.get("version") != BUNDLE_VERSION:
                raise BundleError(f"Unsupported bundle version: {manifest.get('version')}")
            for name in manifest.get("profiles", []):
                entry = f"{name}.zip"
                if not _ENTRY.match(entry) or entry not in bundle.namelist():
                    skipped[str(name)] = "entry missing or has an unsafe name"
                    continue
                if is_running(name):
                    skipped[name] = "running here: stop it first"
                    continue
                inner = bundle.extract(entry, os.path.join(tmp, "x"))
                ok, result = _import_one(pm, inner, name, overwrite, data_dir or DATA_DIR)
                if ok:
                    imported.append(result)
                else:
                    skipped[name] = str(result)
    return {"imported": imported, "skipped": skipped}


def _import_one(pm, zip_path: str, name: str, overwrite: bool, data_dir: str) -> tuple[bool, str]:
    """Import one profile archive. An overwrite starts from an empty data folder (the old one
    is kept as <name>.syncbak and put back if the import fails) so no stale files remain."""
    target = pathlib.Path(data_dir) / name
    backup = pathlib.Path(data_dir) / f"{name}.syncbak"
    moved = False
    if overwrite and name in pm.profiles and target.exists():
        shutil.rmtree(backup, ignore_errors=True)
        target.rename(backup)
        moved = True
    ok, result = pm.import_profile(zip_path, overwrite)
    if not ok and moved:
        shutil.rmtree(target, ignore_errors=True)
        backup.rename(target)
    return ok, str(result)
