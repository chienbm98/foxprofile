"""The packaged app launches the Camoufox build bundled next to it, in place."""

import importlib
import json
import sys

import pytest


def test_bundled_browser_becomes_the_active_build(tmp_path, monkeypatch):
    from camoufox import multiversion, pkgman

    cache = tmp_path / "cache"
    monkeypatch.setattr(multiversion, "INSTALL_DIR", cache)
    monkeypatch.setattr(multiversion, "CONFIG_FILE", cache / "config.json")
    monkeypatch.setattr(multiversion, "COMPAT_FLAG", cache / ".0.5_FLAG")
    monkeypatch.setattr(pkgman, "INSTALL_DIR", cache)
    sys.path.insert(0, "packaging")
    try:
        app = importlib.import_module("foxprofile_app")
    finally:
        sys.path.remove("packaging")

    browser = tmp_path / "App" / "browser"
    browser.mkdir(parents=True)
    (browser / "version.json").write_text(
        json.dumps({"version": "156.0.1", "build": "beta.36", "interface": 1})
    )
    app.use_bundled_browser(browser)
    assert (cache / ".0.5_FLAG").exists()
    assert multiversion.get_active_path() == browser
    assert pkgman.Version.from_path(multiversion.get_active_path()).build == "beta.36"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS bundle layout")
def test_bundled_browser_path_on_macos(tmp_path, monkeypatch):
    sys.path.insert(0, "packaging")
    try:
        app = importlib.import_module("foxprofile_app")
    finally:
        sys.path.remove("packaging")
    contents = tmp_path / "FoxProfile.app" / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources" / "browser").mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(contents / "MacOS" / "FoxProfile"))
    assert app.bundled_browser() is None
    (contents / "Resources" / "browser" / "version.json").write_text("{}")
    assert app.bundled_browser() == (contents / "Resources" / "browser").resolve()
