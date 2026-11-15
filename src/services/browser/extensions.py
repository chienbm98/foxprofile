"""Browser extensions installed into one profile, for either engine.

A profile with `proxy_mode=proton` (chosen in the profile form) opts in;
direct/proxy profiles install nothing and download nothing. The builds come from
the vendors, at run time, and are cached under
`FOXPROFILE_EXTENSIONS_HOME` (default: the FoxProfile cache directory):

    <home>/proton-vpn/firefox/proton-vpn.xpi       signed add-on (AMO)
    <home>/proton-vpn/firefox/meta.json            version + fetch time
    <home>/proton-vpn/chromium/unpacked/           unpacked extension (Chrome Web Store)
    <home>/proton-vpn/chromium/meta.json

Camoufox loads a profile add-on from `<profile>/extensions/<id>.xpi` (signed by
Mozilla; the browser verifies it). fingerprint-chromium is an unbranded
Chromium build, so it still honours `--load-extension=<dir>`; Chrome-branded
builds dropped that switch in 137 and are not what this engine runs.

Extensions are per browser, not per profile state: a profile that already has
the XPI installed keeps using it, and the Chrome engine keeps its unpacked copy
in the profile's extension settings. Updating the cache (`refresh`) replaces the
files on the next launch; browsers apply the new version themselves.

The Proton VPN extension is GPL-3.0 and needs its own Proton account login; it
is not bundled with FoxProfile. When connected it routes the browser around the
profile's proxy, so the exit IP no longer matches the profile's timezone/locale.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from base64 import b64decode
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from ...core.logging import get_logger

logger = get_logger("browser.extensions")

_CHUNK = 1 << 20
_UA = "FoxProfile (anti-detect browser profile manager)"


@dataclass(frozen=True)
class Vendor:
    """One browser build of an extension, plus where it comes from."""

    id: str
    url: str


@dataclass(frozen=True)
class Extension:
    name: str
    label: str
    license: str
    homepage: str
    firefox: Vendor
    chromium: Vendor


PROTON_VPN = Extension(
    name="proton-vpn",
    label="Proton VPN",
    license="GPL-3.0",
    homepage="https://protonvpn.com",
    firefox=Vendor(
        id="vpn@proton.ch",
        url=(
            "https://addons.mozilla.org/firefox/downloads/latest/"
            "proton-vpn-firefox-extension/latest.xpi"
        ),
    ),
    chromium=Vendor(
        id="jplgfhpmjnbigmhklmmbgecoobifkmpa",
        # prodversion only selects the Chrome Web Store update channel. Only CRX3 is
        # accepted: _verify_crx3 checks its signature before anything is unpacked.
        url=(
            "https://clients2.google.com/service/update2/crx?response=redirect"
            "&prodversion=131.0.0.0&acceptformat=crx3"
            "&x=id%3Djplgfhpmjnbigmhklmmbgecoobifkmpa%26uc"
        ),
    ),
)

EXTENSIONS = {extension.name: extension for extension in (PROTON_VPN,)}


class ExtensionError(RuntimeError):
    pass


def _cache_home() -> Path:
    override = os.getenv("FOXPROFILE_EXTENSIONS_HOME")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.getenv("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "foxprofile" / "extensions"


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _download(url: str, dest: Path) -> None:
    """Stream to a per-process part file, then rename into place."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.part")
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as out:
            announced = response.headers.get("Content-Length")
            limit = int(announced) if announced else None
            written = 0
            while chunk := response.read(_CHUNK):
                written += len(chunk)
                if limit is not None and written > limit:
                    raise ExtensionError(f"Unexpected extra data from {url}")
                out.write(chunk)
        if tmp.stat().st_size < 1024:
            raise ExtensionError(f"{url} returned no extension data")
        os.replace(tmp, dest)
    except (OSError, urllib.error.URLError) as e:
        raise ExtensionError(f"Could not download {url}: {e}") from e
    finally:
        tmp.unlink(missing_ok=True)


# Chrome signs a CRX3 over this context, the signed header data and the ZIP payload.
# The trailing NUL belongs to the context.
_CRX3_CONTEXT = b"CRX3 SignedData\x00"


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(buf) or shift > 63:
            raise ExtensionError("Malformed CRX header")
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def _proto_fields(buf: bytes) -> list[tuple[int, bytes]]:
    """The (number, value) pairs of a protobuf message. CRX headers use length-delimited fields only."""
    fields: list[tuple[int, bytes]] = []
    pos = 0
    while pos < len(buf):
        tag, pos = _varint(buf, pos)
        if tag & 7 != 2:
            raise ExtensionError("Unexpected field in CRX header")
        length, pos = _varint(buf, pos)
        if pos + length > len(buf):
            raise ExtensionError("Truncated CRX header")
        fields.append((tag >> 3, buf[pos : pos + length]))
        pos += length
    return fields


def _verify_crx3(data: bytes, expected_id: str) -> bytes:
    """The ZIP payload of a CRX3 file, once its signature proves the expected key signed it.

    Layout: "Cr24", version 3, header length, a protobuf header holding RSA proofs
    (public key + signature) and the signed header data, then the ZIP. A proof
    counts only if the extension id derived from its public key is `expected_id`,
    so an accepted archive was signed by that extension's key.
    """
    if len(data) < 12 or data[:4] != b"Cr24":
        raise ExtensionError("Not a CRX file")
    version = int.from_bytes(data[4:8], "little")
    if version != 3:
        raise ExtensionError(f"Unsupported CRX version: {version}")
    header_length = int.from_bytes(data[8:12], "little")
    header = data[12 : 12 + header_length]
    if len(header) != header_length:
        raise ExtensionError("Truncated CRX header")
    archive = data[12 + header_length :]

    fields = _proto_fields(header)
    signed_header = next((value for number, value in fields if number == 10000), None)
    if signed_header is None:
        raise ExtensionError("The CRX header has no signed data")
    crx_id = dict(_proto_fields(signed_header)).get(1, b"")
    message = _CRX3_CONTEXT + len(signed_header).to_bytes(4, "little") + signed_header + archive

    for number, proof in fields:
        if number != 2:  # sha256_with_rsa; the Web Store does not use ECDSA proofs
            continue
        parts = dict(_proto_fields(proof))
        public_key, signature = parts.get(1, b""), parts.get(2, b"")
        if not public_key or not signature or _extension_id(public_key) != expected_id:
            continue
        try:
            serialization.load_der_public_key(public_key).verify(
                signature, message, padding.PKCS1v15(), hashes.SHA256()
            )
        except (InvalidSignature, TypeError, ValueError) as e:
            raise ExtensionError(f"The signature on the {expected_id} CRX does not verify") from e
        if crx_id != sha256(public_key).digest()[:16]:
            raise ExtensionError("The CRX id does not match its signing key")
        return archive
    raise ExtensionError(f"The CRX is not signed by the {expected_id} key")


def _manifest(data: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            payload = json.loads(archive.read("manifest.json"))
    except (KeyError, ValueError, zipfile.BadZipFile) as e:
        raise ExtensionError(f"Extension archive has no readable manifest.json: {e}") from e
    if not isinstance(payload, dict):
        raise ExtensionError("Extension manifest.json is not an object")
    return payload


def _extension_id(der_public_key: bytes) -> str:
    """The id Chrome derives from a DER public key: SHA-256, first 16 bytes, nibbles as a-p."""
    digest = sha256(der_public_key).digest()[:16]
    return "".join(chr(ord("a") + (byte >> 4)) + chr(ord("a") + (byte & 0xF)) for byte in digest)


def chromium_id(key: str) -> str:
    """The extension id Chrome derives from a manifest `key` (base64 DER key)."""
    return _extension_id(b64decode(key))


def _extract(data: bytes, dest: Path) -> None:
    """Write a ZIP payload to `dest`; the caller renames a fresh temp directory."""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename:
                continue
            target = (dest / info.filename).resolve()
            if target != root and root not in target.parents:
                raise ExtensionError(f"Unsafe path in extension archive: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))


def _store_firefox(extension: Extension, home: Path) -> Path:
    directory = home / extension.name / "firefox"
    xpi = directory / "proton-vpn.xpi"
    meta = directory / "meta.json"
    if xpi.is_file() and meta.is_file():
        return xpi
    _download(extension.firefox.url, xpi)
    manifest = _manifest(xpi.read_bytes())
    gecko = manifest.get("browser_specific_settings", {}).get("gecko", {})
    if gecko.get("id") != extension.firefox.id:
        xpi.unlink(missing_ok=True)
        raise ExtensionError(
            f"{extension.label}: the add-on id is {gecko.get('id')!r}, expected "
            f"{extension.firefox.id!r}"
        )
    _write_json(
        meta,
        {
            "name": extension.name,
            "engine": "firefox",
            "version": manifest.get("version", ""),
            "id": extension.firefox.id,
            "source": extension.firefox.url,
            "fetched": int(time.time()),
        },
    )
    logger.info("Fetched %s %s (Firefox)", extension.label, manifest.get("version", ""))
    return xpi


def _store_chromium(extension: Extension, home: Path) -> Path:
    directory = home / extension.name / "chromium"
    unpacked = directory / "unpacked"
    meta = directory / "meta.json"
    if (unpacked / "manifest.json").is_file() and meta.is_file():
        return unpacked
    # An interrupted earlier run may have left a directory with no marker: the
    # download below is a different build, so do not keep the stale copy.
    if unpacked.exists() and not meta.is_file():
        shutil.rmtree(unpacked, ignore_errors=True)
    _download(extension.chromium.url, directory / "extension.crx")
    data = _verify_crx3((directory / "extension.crx").read_bytes(), extension.chromium.id)
    manifest = _manifest(data)
    key = manifest.get("key")
    if not key:
        raise ExtensionError(
            f"{extension.label}: the Chrome build has no manifest key, so its id would "
            "change between launches and logins would not stick"
        )
    if chromium_id(key) != extension.chromium.id:
        raise ExtensionError(
            f"{extension.label}: the Chrome build id is {chromium_id(key)!r}, expected "
            f"{extension.chromium.id!r}"
        )
    temporary = directory / f".unpacked-{os.getpid()}"
    shutil.rmtree(temporary, ignore_errors=True)
    try:
        _extract(data, temporary)
        if unpacked.exists():
            # A concurrent launch installed it first; both copies are identical.
            shutil.rmtree(temporary, ignore_errors=True)
        else:
            try:
                os.replace(temporary, unpacked)
            except OSError:
                # Windows refuses a directory replace while a browser has it open.
                shutil.rmtree(temporary, ignore_errors=True)
                if not (unpacked / "manifest.json").is_file():
                    raise
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    _write_json(
        meta,
        {
            "name": extension.name,
            "engine": "chromium",
            "version": manifest.get("version", ""),
            "id": extension.chromium.id,
            "source": extension.chromium.url,
            "fetched": int(time.time()),
        },
    )
    logger.info("Fetched %s %s (Chromium)", extension.label, manifest.get("version", ""))
    return unpacked


def _install_firefox(extension: Extension, profile_dir: Path, home: Path) -> str:
    xpi = _store_firefox(extension, home)
    extensions_dir = profile_dir / "extensions"
    extensions_dir.mkdir(parents=True, exist_ok=True)
    target = extensions_dir / f"{extension.firefox.id}.xpi"
    # Firefox discovers profile add-ons by <addon-id>.xpi. The marker records
    # which cached build produced the copy, so an updated download is applied
    # and an unchanged one is left alone (cookies and the add-on's storage stay).
    marker = profile_dir / ".foxprofile-extensions.json"
    state = _read_json(marker)
    stat = xpi.stat()
    signature = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    if not target.is_file() or state.get(extension.name) != signature:
        tmp = target.with_name(f".{target.name}.{os.getpid()}.part")
        shutil.copyfile(xpi, tmp)
        os.replace(tmp, target)
        state[extension.name] = signature
        _write_json(marker, state)
    meta = _read_json(home / extension.name / "firefox" / "meta.json")
    return f"{extension.label} {meta.get('version', '')}".strip()


def install_firefox(profile_dir: str | Path, names: tuple[str, ...]) -> list[str]:
    """Ensure the requested add-ons are in a Camoufox profile; return labels.

    Called by the Camoufox runner before the browser starts. Raises
    ExtensionError; the runner logs it and launches without the extension.
    """
    if not names:
        return []
    home = _cache_home()
    installed: list[str] = []
    for name in names:
        extension = EXTENSIONS.get(name)
        if extension is None:
            continue
        installed.append(_install_firefox(extension, Path(profile_dir), home))
    return installed


def remove_firefox(profile_dir: str | Path) -> list[str]:
    """Delete the add-ons this module installed; never ones the user added.

    Called when a profile no longer selects an extension, so unchecking it
    actually removes it on the next launch. The marker records what we wrote.
    """
    profile = Path(profile_dir)
    marker = profile / ".foxprofile-extensions.json"
    state = _read_json(marker)
    if not state:
        return []
    removed: list[str] = []
    for name in list(state):
        extension = EXTENSIONS.get(name)
        if extension is None:
            continue
        target = profile / "extensions" / f"{extension.firefox.id}.xpi"
        if target.is_file():
            try:
                target.unlink()
            except OSError as e:
                logger.warning("Could not remove %s from %s: %s", name, profile.name, e)
                continue
            removed.append(name)
        state.pop(name, None)
    if state:
        _write_json(marker, state)
    else:
        marker.unlink(missing_ok=True)
    return removed


def chromium_extra_args(names: tuple[str, ...]) -> list[str]:
    """`--load-extension=` for the Chrome engine, or [] when nothing is requested."""
    if not names:
        return []
    home = _cache_home()
    directories = [
        str(_store_chromium(EXTENSIONS[name], home)) for name in names if name in EXTENSIONS
    ]
    return [f"--load-extension={','.join(directories)}"] if directories else []


def installed_versions(names: tuple[str, ...] | None = None) -> dict[str, dict]:
    """Cache metadata per extension, for `python -m ...extensions list` and logs."""
    wanted = tuple(EXTENSIONS) if names is None else names
    home = _cache_home()
    return {
        name: {
            "firefox": _read_json(home / name / "firefox" / "meta.json"),
            "chromium": _read_json(home / name / "chromium" / "meta.json"),
        }
        for name in wanted
    }


def refresh(names: tuple[str, ...] | None = None) -> list[str]:
    """Delete the cached builds and fetch them again (next launch applies them)."""
    wanted = tuple(EXTENSIONS) if names is None else names
    home = _cache_home()
    fetched: list[str] = []
    for name in wanted:
        extension = EXTENSIONS.get(name)
        if extension is None:
            continue
        shutil.rmtree(home / name, ignore_errors=True)
        _store_firefox(extension, home)
        _store_chromium(extension, home)
        fetched.append(extension.label)
    return fetched


def _main(argv: list[str]) -> int:
    command = argv[0] if argv else "list"
    if command == "list":
        versions = installed_versions()
        if not versions:
            print("No extension fetched (python -m src.services.browser.extensions fetch)")
        for name, engines in versions.items():
            for engine, meta in engines.items():
                state = (
                    f"{meta.get('version', '?')} ({meta.get('source', '')})"
                    if meta
                    else "not fetched"
                )
                print(f"{name} [{engine}]: {state}")
        return 0
    if command in ("fetch", "refresh"):
        fetched = refresh()
        print(("Updated: " + ", ".join(fetched)) if fetched else "No extension fetched")
        return 0
    print("Usage: python -m src.services.browser.extensions [list|fetch]")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
