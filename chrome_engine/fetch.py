"""Download, verify and unpack a pinned fingerprint-chromium build.

Layout under the engine home (see `engine_home`):

    <home>/<version>/            the unpacked browser
    <home>/<version>/.installed  JSON marker written last; no marker, no install

An install is built in a temporary sibling directory and renamed into place,
so an interrupted download or extraction never leaves a half-usable browser.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from .release import Asset, Release, get_release, host_platform

MARKER = ".installed"
_CHUNK = 1 << 20
_EXECUTABLE_NAMES = ("chrome.exe", "chrome", "Chromium")

Progress = Callable[[int, int], None]


class FetchError(RuntimeError):
    pass


def engine_home() -> Path:
    """Where browser builds are kept. FOXPROFILE_CHROME_HOME overrides it."""
    override = os.getenv("FOXPROFILE_CHROME_HOME")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.getenv("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "foxprofile" / "chrome"


def installed_executable(version: str | None = None, home: Path | None = None) -> Path | None:
    """The browser executable of an installed version, or None."""
    release = get_release(version)
    marker = (home or engine_home()) / release.version / MARKER
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    exe = marker.parent / data.get("executable", "")
    return exe if exe.is_file() else None


def install(
    version: str | None = None,
    home: Path | None = None,
    progress: Progress | None = None,
    host: str | None = None,
) -> Path:
    """Install a pinned build if needed and return its executable.

    Safe across processes (FoxProfile prefetches while runners may launch): one
    process holds `<version>.lock` and installs; the others wait for it, then
    use its install instead of downloading the build again.
    """
    release = get_release(version)
    home = home or engine_home()
    existing = installed_executable(release.version, home)
    if existing:
        return existing
    asset = release.asset_for(host or host_platform())
    home.mkdir(parents=True, exist_ok=True)
    lock = home / f"{release.version}.lock"
    while not _try_lock(lock):
        _wait_for_lock(lock, release, asset, home, progress)
        existing = installed_executable(release.version, home)
        if existing:
            return existing
    try:
        existing = installed_executable(release.version, home)
        if existing:
            return existing
        _remove_leftovers(home, release.version)
        archive = home / f"{release.version}.{asset.kind}.{os.getpid()}.part"
        try:
            download(asset, archive, progress)
            return unpack(release, asset, archive, home)
        finally:
            with contextlib.suppress(OSError):
                archive.unlink()
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


_POLL_SECONDS = 1.0
_RENAME_ATTEMPTS = 10
_RENAME_DELAY = 0.5
# A lock older than this is abandoned even if its PID was reused by another process.
_LOCK_MAX_AGE = 3600


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_owner(lock: Path) -> int | None:
    """The PID holding `lock`, or None when the lock is free or abandoned."""
    try:
        pid = int(lock.read_text(encoding="utf-8").strip() or 0)
        age = time.time() - lock.stat().st_mtime
    except (OSError, ValueError):
        return None
    return pid if _pid_alive(pid) and age < _LOCK_MAX_AGE else None


def _try_lock(lock: Path) -> bool:
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if _lock_owner(lock) is None:
            # Abandoned by a killed process: take it over on the next attempt.
            with contextlib.suppress(OSError):
                lock.unlink()
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return True


def _wait_for_lock(
    lock: Path, release: Release, asset: Asset, home: Path, progress: Progress | None
) -> None:
    """Wait while another live process installs, reporting its download progress."""
    while (owner := _lock_owner(lock)) is not None:
        if installed_executable(release.version, home):
            return
        if progress:
            part = home / f"{release.version}.{asset.kind}.{owner}.part"
            with contextlib.suppress(OSError):
                progress(min(part.stat().st_size, asset.size), asset.size)
        time.sleep(_POLL_SECONDS)


def _remove_leftovers(home: Path, version: str) -> None:
    """Delete partial downloads and staging dirs left by killed installs.

    Only called while holding the install lock, so nothing here is in use.
    """
    for part in home.glob(f"{version}.*.part"):
        with contextlib.suppress(OSError):
            part.unlink()
    for staging in home.glob(f".{version}-*"):
        if staging.is_dir():
            shutil.rmtree(staging, ignore_errors=True)


def download(asset: Asset, dest: Path, progress: Progress | None = None) -> None:
    """Stream `asset` to `dest`, failing unless its SHA-256 matches the pin."""
    digest = hashlib.sha256()
    done = 0
    request = urllib.request.Request(asset.url, headers={"User-Agent": "foxprofile-chrome-engine"})
    try:
        with urllib.request.urlopen(request, timeout=60) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length") or asset.size)
            while chunk := resp.read(_CHUNK):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except OSError as e:
        raise FetchError(f"Download failed: {asset.url}: {e}") from e
    if digest.hexdigest() != asset.sha256:
        raise FetchError(
            f"Checksum mismatch for {asset.url}: expected {asset.sha256}, got {digest.hexdigest()}"
        )


def unpack(release: Release, asset: Asset, archive: Path, home: Path) -> Path:
    """Extract a verified archive into <home>/<version> and return the executable."""
    target = home / release.version
    staging = Path(tempfile.mkdtemp(prefix=f".{release.version}-", dir=home))
    try:
        if asset.kind == "zip":
            with zipfile.ZipFile(archive) as zf:
                _check_members(zf.namelist())
                zf.extractall(staging)
        elif asset.kind == "tar.xz":
            with tarfile.open(archive, "r:xz") as tf:
                _check_members(tf.getnames())
                _extract_tar(tf, staging)
        elif asset.kind == "dmg":
            _extract_dmg(archive, staging)
        else:
            raise FetchError(f"Unknown archive kind {asset.kind}")

        exe = _locate_executable(staging, asset.executable)
        _make_executable(exe)
        relative = exe.relative_to(staging).as_posix()
        # Another process finished first: keep its copy, which may already be running.
        finished = installed_executable(release.version, home)
        if finished:
            shutil.rmtree(staging, ignore_errors=True)
            return finished
        (staging / MARKER).write_text(
            json.dumps(
                {"version": release.version, "sha256": asset.sha256, "executable": relative}
            ),
            encoding="utf-8",
        )
        # A target without a marker is an unfinished copy; one with a marker is
        # in use and is never removed.
        if target.exists() and not installed_executable(release.version, home):
            shutil.rmtree(target, ignore_errors=True)
        for attempt in range(_RENAME_ATTEMPTS):
            try:
                staging.rename(target)
                break
            except OSError:
                finished = installed_executable(release.version, home)
                if finished:
                    shutil.rmtree(staging, ignore_errors=True)
                    return finished
                if attempt == _RENAME_ATTEMPTS - 1:
                    raise
                # Antivirus and indexers hold freshly extracted files for a moment.
                time.sleep(_RENAME_DELAY)
        return target / relative
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _check_members(names: list[str]) -> None:
    # The archive is pinned by hash, but refuse path traversal anyway.
    for name in names:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise FetchError(f"Unsafe path in archive: {name}")


def _extract_tar(tf: tarfile.TarFile, dest: Path) -> None:
    if hasattr(tarfile, "data_filter"):
        tf.extractall(dest, filter="data")
    else:  # Python < 3.10.12 / 3.11.4: no filters, so keep only plain files and dirs
        tf.extractall(dest, members=[m for m in tf.getmembers() if m.isfile() or m.isdir()])


def _extract_dmg(archive: Path, dest: Path) -> None:
    if sys.platform != "darwin":
        raise FetchError("A .dmg build can only be unpacked on macOS")
    mount = Path(tempfile.mkdtemp(prefix="fpchrome-mnt-"))
    subprocess.run(
        ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(archive)],
        check=True,
        capture_output=True,
    )
    try:
        apps = list(mount.glob("*.app"))
        if not apps:
            raise FetchError("No .app bundle in the disk image")
        shutil.copytree(apps[0], dest / apps[0].name, symlinks=True)
    finally:
        subprocess.run(["hdiutil", "detach", str(mount), "-force"], capture_output=True)
        shutil.rmtree(mount, ignore_errors=True)


def _locate_executable(root: Path, expected: str) -> Path:
    exe = root / expected
    if exe.is_file():
        return exe
    # Release layouts have changed between versions; fall back to a search.
    for name in _EXECUTABLE_NAMES:
        for candidate in sorted(root.rglob(name)):
            if candidate.is_file() and (name != "Chromium" or candidate.parent.name == "MacOS"):
                return candidate
    raise FetchError(f"Browser executable not found in the archive (expected {expected})")


def _make_executable(path: Path) -> None:
    if not sys.platform.startswith("win"):
        path.chmod(path.stat().st_mode | 0o755)


def uninstall(version: str | None = None, home: Path | None = None) -> bool:
    release = get_release(version)
    target = (home or engine_home()) / release.version
    if not target.exists():
        return False
    shutil.rmtree(target)
    return True
