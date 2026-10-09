"""Engine behaviour that needs no browser."""

import asyncio
import json

import pytest

from chrome_engine import engine as engine_mod
from chrome_engine.engine import (
    IGNORED_DEFAULT_ARGS,
    ChromeEngine,
    EngineError,
    EngineNotInstalled,
    build_args,
)
from chrome_engine.persona import Persona

P = Persona(seed=5, platform="windows", platform_version="15.0.0", hardware_concurrency=8)


def test_build_args_headed():
    args = build_args(P)
    assert args[:5] == P.to_args()
    assert "--start-maximized" in args
    assert not any(a.startswith("--disable-features") for a in args)
    assert not any(a.startswith("--proxy-server") for a in args)


def test_build_args_headless_sets_a_real_screen():
    args = build_args(P, headless=True)
    assert "--window-size=1920,1080" in args
    assert "--screen-info={0,0 1920x1080}" in args
    assert "--start-maximized" not in args


def test_build_args_offscreen():
    args = build_args(P, headless="offscreen")
    assert "--window-position=-32000,-32000" in args


def test_build_args_proxy_and_extra_come_last():
    args = build_args(P, proxy_url="http://127.0.0.1:5555", extra_args=["--foo"])
    assert "--proxy-server=http://127.0.0.1:5555" in args
    assert args[-1] == "--foo"


def test_playwright_feature_switch_is_found():
    switch = engine_mod.playwright_disabled_features_arg()
    assert switch is not None, "update the parser for this Playwright version"
    assert switch.startswith("--disable-features=")
    assert "ThirdPartyStoragePartitioning" in switch
    assert " " not in switch and '"' not in switch


def test_ignored_args_include_playwright_features(tmp_path):
    ignored = ChromeEngine(tmp_path)._ignored_default_args()
    assert engine_mod.playwright_disabled_features_arg() in ignored


def test_unparseable_playwright_features_warn(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_mod, "playwright_disabled_features_arg", lambda: None)
    eng = ChromeEngine(tmp_path)
    assert eng._ignored_default_args() == list(IGNORED_DEFAULT_ARGS)
    assert "storage partitioning" in eng.warnings[0]


def test_ignored_defaults_cover_page_visible_switches():
    for switch in (
        "--enable-automation",
        "--disable-popup-blocking",
        "--hide-scrollbars",
        "--force-color-profile=srgb",
        "--disable-back-forward-cache",
        "--no-sandbox",
    ):
        assert switch in IGNORED_DEFAULT_ARGS


def test_headless_value_is_validated(tmp_path):
    with pytest.raises(ValueError):
        ChromeEngine(tmp_path, headless="virtual")


def test_missing_executable(tmp_path):
    eng = ChromeEngine(tmp_path, executable=tmp_path / "nope.exe")
    with pytest.raises(EngineNotInstalled):
        asyncio.run(eng.start())


def test_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_mod.fetch, "installed_executable", lambda v=None: None)
    with pytest.raises(EngineNotInstalled, match="python -m chrome_engine fetch"):
        asyncio.run(ChromeEngine(tmp_path).start())


def _resolve(tmp_path, monkeypatch, host, **kwargs):
    monkeypatch.setattr(engine_mod, "host_os", lambda: host)
    eng = ChromeEngine(tmp_path, **kwargs)
    return eng, eng._resolve_persona()


def test_unsupported_persona_is_refused(tmp_path, monkeypatch):
    with pytest.raises(EngineError, match="cannot be presented consistently"):
        _resolve(tmp_path, monkeypatch, "windows", platform="linux")


def test_unsupported_persona_can_be_forced(tmp_path, monkeypatch):
    eng, persona = _resolve(
        tmp_path, monkeypatch, "windows", platform="linux", allow_unsupported=True
    )
    assert persona.platform == "linux"
    assert eng.warnings


def test_cross_os_persona_warns(tmp_path, monkeypatch):
    eng, persona = _resolve(tmp_path, monkeypatch, "windows", platform="macos")
    assert persona.platform == "macos"
    assert "fonts" in eng.warnings[0]


def test_platform_defaults_to_host(tmp_path, monkeypatch):
    eng, persona = _resolve(tmp_path, monkeypatch, "linux")
    assert persona.platform == "linux"
    assert eng.warnings == []


def test_explicit_persona_with_pins(tmp_path, monkeypatch):
    eng, persona = _resolve(
        tmp_path, monkeypatch, "windows", persona=P, timezone="Asia/Tokyo", locale="ja-JP"
    )
    assert (persona.seed, persona.timezone, persona.locale) == (5, "Asia/Tokyo", "ja-JP")


def test_saved_persona_is_reused(tmp_path, monkeypatch):
    _, first = _resolve(tmp_path, monkeypatch, "windows")
    _, second = _resolve(tmp_path, monkeypatch, "windows")
    assert first == second


def test_geo_failure_behind_a_proxy_refuses_to_launch(tmp_path, monkeypatch):
    """Launching anyway would show the host's timezone through the proxy."""

    def boom(url):
        raise OSError("no route")

    monkeypatch.setattr(engine_mod, "lookup", boom)
    exe = tmp_path / "chrome.exe"
    exe.write_bytes(b"")
    eng = ChromeEngine(tmp_path / "p", executable=exe, proxy="http://u:p@127.0.0.1:9")
    with pytest.raises(EngineError, match="exit IP"):
        asyncio.run(eng.start())
    # start() cleaned up the bridge it had opened.
    assert eng.bridge is None


def test_geo_is_skipped_when_pinned(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_mod, "lookup", lambda url: pytest.fail("looked up"))
    eng = ChromeEngine(
        tmp_path / "p",
        executable=__file__,
        proxy="http://127.0.0.1:9",
        timezone="Europe/Paris",
        locale="fr-FR",
    )

    import playwright.async_api as pw

    class Fake:
        async def start(self):
            raise RuntimeError("stop before the browser")

    monkeypatch.setattr(pw, "async_playwright", lambda: Fake())
    with pytest.raises(RuntimeError, match="stop before the browser"):
        asyncio.run(eng.start())
    assert eng.persona.timezone == "Europe/Paris"
    assert eng.geo is None
    assert "--timezone=Europe/Paris" in eng.args
    assert any(a.startswith("--proxy-server=http://127.0.0.1:") for a in eng.args)


def test_webrtc_policy_on_a_fresh_profile(tmp_path):
    engine_mod.set_webrtc_policy(tmp_path, engine_mod.WEBRTC_POLICY_PROXY)
    prefs = json.loads((tmp_path / "Default" / "Preferences").read_text("utf-8"))
    assert prefs == {"webrtc": {"ip_handling_policy": "disable_non_proxied_udp"}}


def test_webrtc_policy_keeps_other_preferences(tmp_path):
    path = tmp_path / "Default" / "Preferences"
    path.parent.mkdir()
    path.write_text(
        json.dumps({"profile": {"name": "x"}, "webrtc": {"multiple_routes_enabled": False}})
    )
    engine_mod.set_webrtc_policy(tmp_path, engine_mod.WEBRTC_POLICY_DIRECT)
    prefs = json.loads(path.read_text("utf-8"))
    assert prefs["profile"] == {"name": "x"}
    assert prefs["webrtc"] == {
        "multiple_routes_enabled": False,
        "ip_handling_policy": "default_public_interface_only",
    }
    assert not list(path.parent.glob("*tmp*"))


def test_webrtc_policy_replaces_a_corrupt_file(tmp_path):
    path = tmp_path / "Default" / "Preferences"
    path.parent.mkdir()
    path.write_text("{broken")
    engine_mod.set_webrtc_policy(tmp_path, engine_mod.WEBRTC_POLICY_PROXY)
    assert (
        json.loads(path.read_text("utf-8"))["webrtc"]["ip_handling_policy"]
        == "disable_non_proxied_udp"
    )


def test_webrtc_policy_switches_with_the_proxy(tmp_path):
    engine_mod.set_webrtc_policy(tmp_path, engine_mod.WEBRTC_POLICY_PROXY)
    engine_mod.set_webrtc_policy(tmp_path, engine_mod.WEBRTC_POLICY_DIRECT)
    prefs = json.loads((tmp_path / "Default" / "Preferences").read_text("utf-8"))
    assert prefs["webrtc"]["ip_handling_policy"] == "default_public_interface_only"


def test_start_twice_is_refused(tmp_path):
    eng = ChromeEngine(tmp_path)
    eng.context = object()
    with pytest.raises(EngineError, match="already running"):
        asyncio.run(eng.start())


def test_runner_installs_the_engine_on_first_launch(monkeypatch, capsys):
    import asyncio

    from chrome_engine import fetch, runner

    installed = []
    monkeypatch.setattr(
        fetch, "installed_executable", lambda *a, **k: installed[0] if installed else None
    )

    def fake_install(progress=None):
        for done in (0, 50, 100, 100, 100):
            progress(done, 100)
        installed.append("chrome")
        return "chrome"

    monkeypatch.setattr(fetch, "install", fake_install)
    asyncio.run(runner.ensure_installed())
    out = capsys.readouterr().out
    assert "downloading it once" in out
    assert out.count("Downloading Chrome engine: 100%") == 1
    assert "Chrome engine installed" in out

    # Already installed: nothing is printed or downloaded.
    asyncio.run(runner.ensure_installed())
    assert capsys.readouterr().out == ""
