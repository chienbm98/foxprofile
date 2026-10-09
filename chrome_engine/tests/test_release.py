import re

import pytest

from chrome_engine import release
from chrome_engine.release import UnsupportedPlatformError


def test_default_version_is_pinned_for_every_platform():
    rel = release.get_release()
    assert rel.version == release.DEFAULT_VERSION
    assert set(rel.assets) == {"windows-x64", "linux-x64", "macos"}
    for asset in rel.assets.values():
        assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256)
        assert asset.size > 50_000_000
        assert asset.url.startswith("https://github.com/adryfish/fingerprint-chromium/releases/")
        assert rel.version in asset.url


def test_150_is_not_the_default():
    # 150.0.7871.186 crashes the renderer when an emoji is drawn on a canvas.
    assert not release.DEFAULT_VERSION.startswith("150.")


def test_unknown_version():
    with pytest.raises(ValueError, match="Unknown fingerprint-chromium version"):
        release.get_release("1.2.3")


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("win32", "AMD64", "windows-x64"),
        ("linux", "x86_64", "linux-x64"),
        ("darwin", "arm64", "macos"),
    ],
)
def test_host_platform(system, machine, expected):
    assert release.host_platform(system, machine) == expected


@pytest.mark.parametrize(
    ("system", "machine"),
    [("linux", "aarch64"), ("win32", "ARM64"), ("freebsd", "amd64"), ("darwin", "x86_64")],
)
def test_host_platform_unsupported(system, machine):
    with pytest.raises(UnsupportedPlatformError):
        release.host_platform(system, machine)


@pytest.mark.parametrize(
    ("system", "expected"), [("win32", "windows"), ("darwin", "macos"), ("linux", "linux")]
)
def test_host_os(system, expected):
    assert release.host_os(system) == expected


def test_asset_for_missing_platform():
    with pytest.raises(UnsupportedPlatformError, match="no build for"):
        release.get_release().asset_for("linux-arm64")


def test_rosetta_python_counts_as_apple_silicon(monkeypatch):
    monkeypatch.setattr(release.sys, "platform", "darwin")
    monkeypatch.setattr(release.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(release, "_under_rosetta", lambda: True)
    assert release.host_platform() == "macos"


def test_intel_mac_is_unsupported(monkeypatch):
    monkeypatch.setattr(release.sys, "platform", "darwin")
    monkeypatch.setattr(release.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(release, "_under_rosetta", lambda: False)
    with pytest.raises(UnsupportedPlatformError):
        release.host_platform()
