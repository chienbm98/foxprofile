"""The fingerprint-chromium builds this engine is tested against.

Builds come from https://github.com/adryfish/fingerprint-chromium (BSD-3,
based on ungoogled-chromium). Each one is pinned by SHA-256 because the
browser is downloaded at run time and then trusted with cookies and proxies.

150.0.7871.186 is deliberately not the default: drawing an emoji onto a 2D
canvas crashes its renderer in about half of all launches while canvas
spoofing is on, and fingerprinting scripts draw emoji all the time. 148 does
not. tests/test_browser.py::test_emoji_canvas_does_not_crash guards this when
the pin moves.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass

_BASE = "https://github.com/adryfish/fingerprint-chromium/releases/download"


@dataclass(frozen=True)
class Asset:
    url: str
    sha256: str
    size: int
    # "zip", "tar.xz" or "dmg"
    kind: str
    # Path of the browser executable inside the extracted archive.
    executable: str


@dataclass(frozen=True)
class Release:
    version: str
    assets: dict[str, Asset]

    def asset_for(self, host: str) -> Asset:
        try:
            return self.assets[host]
        except KeyError:
            raise UnsupportedPlatformError(
                f"fingerprint-chromium {self.version} has no build for {host}; "
                f"available: {', '.join(sorted(self.assets))}"
            ) from None


class UnsupportedPlatformError(RuntimeError):
    pass


def _release(
    version: str, windows: tuple[str, int], linux: tuple[str, int], macos: tuple[str, int]
) -> Release:
    folder = f"ungoogled-chromium_{version}-1.1_windows_x64"
    return Release(
        version=version,
        assets={
            "windows-x64": Asset(
                url=f"{_BASE}/{version}/{folder}.zip",
                sha256=windows[0],
                size=windows[1],
                kind="zip",
                executable=f"{folder}/chrome.exe",
            ),
            "linux-x64": Asset(
                url=f"{_BASE}/{version}/ungoogled-chromium-{version}-1-x86_64_linux.tar.xz",
                sha256=linux[0],
                size=linux[1],
                kind="tar.xz",
                executable=f"ungoogled-chromium-{version}-1-x86_64_linux/chrome",
            ),
            "macos": Asset(
                url=f"{_BASE}/{version}/ungoogled-chromium_{version}-1.1_macos.dmg",
                sha256=macos[0],
                size=macos[1],
                kind="dmg",
                executable="Chromium.app/Contents/MacOS/Chromium",
            ),
        },
    )


RELEASES: dict[str, Release] = {
    r.version: r
    for r in (
        _release(
            "148.0.7778.215",
            windows=("9ef3f471b7a6641b4224532522b29141ce3746e27d55788d88e2fd951f362579", 189767686),
            linux=("70d239830332e5820aa34dfcb284161cac0429eee25da642830afe04bda717f4", 141269020),
            macos=("b72f091e2e1a7583eed389c4b8e3534ed355e568af8c8bbf8fc30a25e23ca679", 140187500),
        ),
    )
}

DEFAULT_VERSION = "148.0.7778.215"


def get_release(version: str | None = None) -> Release:
    version = version or DEFAULT_VERSION
    try:
        return RELEASES[version]
    except KeyError:
        raise ValueError(
            f"Unknown fingerprint-chromium version {version}; pinned: {', '.join(RELEASES)}"
        ) from None


def _under_rosetta() -> bool:
    """True for an x86_64 process translated by Rosetta on an Apple Silicon Mac."""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.stdout.strip() == "1"


def _host_machine() -> str:
    machine = platform.machine().lower()
    # An x86_64 Python under Rosetta still runs on an arm64 Mac.
    if sys.platform == "darwin" and machine == "x86_64" and _under_rosetta():
        return "arm64"
    return machine


def host_platform(system: str | None = None, machine: str | None = None) -> str:
    """The asset key for this machine: windows-x64, linux-x64 or macos."""
    system = (system or sys.platform).lower()
    machine = (machine or _host_machine()).lower()
    if system.startswith("win"):
        if machine in ("amd64", "x86_64"):
            return "windows-x64"
    elif system.startswith("linux"):
        if machine in ("x86_64", "amd64"):
            return "linux-x64"
    # The macOS build is arm64 only (Mach-O thin); it cannot run on Intel Macs.
    elif system == "darwin" and machine in ("arm64", "aarch64"):
        return "macos"
    raise UnsupportedPlatformError(f"No fingerprint-chromium build for {system}/{machine}")


def host_os(system: str | None = None) -> str:
    """The persona platform name of this machine: windows, macos or linux."""
    system = (system or sys.platform).lower()
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "macos"
    return "linux"
