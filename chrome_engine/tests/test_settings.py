"""FoxProfile's fingerprint settings applied to the Chrome engine.

The plan/prefs/persona tests need no browser; the last group launches the real
build (skipped unless installed) and reads the effect back through the probe page.
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest

from chrome_engine import engine as engine_mod
from chrome_engine import persona as personas
from chrome_engine import probe
from chrome_engine import settings as fpmap
from chrome_engine.engine import ChromeEngine
from chrome_engine.geo import ExitGeo
from chrome_engine.release import host_os
from src.services.browser import fpsettings

HOST = host_os()


def settings(**items):
    """Full Chrome settings with `item=(mode, value)` overrides."""
    out = fpsettings.defaults(HOST, "chrome")
    for name, (mode, *value) in items.items():
        out[name] = {"mode": mode, "value": value[0] if value else None}
    return fpsettings.normalize(out, HOST, "chrome")


# --- Plan ------------------------------------------------------------------------


def test_defaults_only_turn_off_canvas_noise():
    plan = fpmap.plan(settings(), 10)
    assert plan.args() == ["--disable-spoofing=canvas"]
    assert plan.cores is None and plan.timezone is None and plan.locale is None
    assert plan.follow == {"timezone", "locale", "geolocation"}


def test_real_modes_become_switches():
    plan = fpmap.plan(
        settings(canvas=("real",), audio=("real",), webgl_meta=("real",), webrtc=("real",),
                 port_scan=("real",)),
        10,
    )  # fmt: skip
    assert plan.args() == [
        "--disable-spoofing=canvas,audio,gpu",
        "--webrtc-ip-handling-policy=default",
        "--disable-features=LocalNetworkAccessChecks",
    ]


def test_cores_timezone_language_geolocation():
    pos = {"latitude": 35.68, "longitude": 139.69, "accuracy": 30}
    plan = fpmap.plan(
        settings(
            hardware_concurrency=("custom", 6),
            timezone=("custom", "Asia/Tokyo"),
            language=("custom", "vi-VN,en-US"),
            geolocation=("custom", pos),
        ),
        10,
    )
    assert (plan.cores, plan.timezone, plan.locale, plan.position) == (
        6,
        "Asia/Tokyo",
        "vi-VN",
        pos,
    )
    assert plan.follow == frozenset()
    assert fpmap.plan(settings(hardware_concurrency=("real",)), 128).cores == 64
    real = fpmap.plan(settings(timezone=("real",), language=("real",)), 8)
    assert (real.timezone, real.locale, real.follow) == (None, None, {"geolocation"})


def test_prefs_are_written_for_every_mode():
    def prefs(proxied=False, **items):
        return fpmap.plan(settings(**items), 8).prefs(proxied)

    assert prefs()["webrtc.ip_handling_policy"] == fpmap.WEBRTC_DIRECT
    assert prefs(True)["webrtc.ip_handling_policy"] == fpmap.WEBRTC_PROXY
    assert prefs(webrtc=("off",))["webrtc.ip_handling_policy"] == fpmap.WEBRTC_PROXY
    assert prefs(webrtc=("real",))["webrtc.ip_handling_policy"] == "default"
    geo = "profile.default_content_setting_values.geolocation"
    assert prefs()[geo] == 3 and prefs(geo_permission=("allow",))[geo] == 3
    assert prefs(geo_permission=("block",))[geo] == 2
    lna = "profile.default_content_setting_values.local_network_access"
    assert prefs()[lna] == 2 and prefs(port_scan=("real",))[lna] is None


def test_set_prefs_merges_removes_and_skips_needless_writes(tmp_path):
    path = tmp_path / "Default" / "Preferences"
    path.parent.mkdir()
    path.write_text(json.dumps({"keep": 1, "profile": {"x": 1}}), encoding="utf-8")
    engine_mod.set_prefs(
        tmp_path, {"profile.default_content_setting_values.geolocation": 2, "a.b": 3}
    )
    prefs = json.loads(path.read_text("utf-8"))
    assert prefs["keep"] == 1 and prefs["profile"]["x"] == 1
    assert prefs["profile"]["default_content_setting_values"]["geolocation"] == 2
    assert prefs["a"]["b"] == 3
    engine_mod.set_prefs(tmp_path, {"profile.default_content_setting_values.geolocation": None})
    assert (
        "geolocation"
        not in json.loads(path.read_text("utf-8"))["profile"]["default_content_setting_values"]
    )
    before = path.stat().st_mtime_ns
    engine_mod.set_prefs(tmp_path, {"never.there": None})  # nothing to remove: no write
    assert path.stat().st_mtime_ns == before


def test_first_locale_accepts_only_what_a_persona_can_hold():
    assert fpmap.first_locale("en-US,vi-VN") == "en-US"
    assert fpmap.first_locale("zh") == "zh"
    assert fpmap.first_locale("zh-Hans-CN") is None and fpmap.first_locale("") is None


# --- Precedence and persona handling (no browser) ----------------------------------


def make(tmp_path, **kw):
    return ChromeEngine(tmp_path, platform=HOST, **kw)


def test_settings_win_over_arguments_and_the_saved_persona(tmp_path):
    saved = personas.generate(HOST, seed=99, timezone="Asia/Seoul", locale="ko-KR")
    personas.save(tmp_path, saved)
    eng = make(
        tmp_path,
        timezone="Asia/Singapore",  # profile.timezone as the runner used to pass it
        locale="th-TH",
        settings=settings(timezone=("custom", "Europe/Paris"), language=("custom", "de-DE")),
    )
    persona = eng._resolve_persona()
    assert (persona.timezone, persona.locale) == ("Europe/Paris", "de-DE")
    assert persona.seed == 99


def test_mask_and_real_clear_a_pinned_value_but_nothing_is_saved(tmp_path):
    saved = personas.generate(HOST, seed=99, timezone="Asia/Seoul", locale="ko-KR")
    personas.save(tmp_path, saved)
    for mode in ("mask", "real"):
        eng = make(tmp_path, settings=settings(timezone=(mode,), language=(mode,)))
        persona = eng._resolve_persona()
        assert (persona.timezone, persona.locale) == (None, None)
    # The file still holds what was there: settings never write the persona.
    assert personas.load(tmp_path) == saved


def test_cores_come_from_the_settings_without_changing_the_saved_device(tmp_path):
    seeded = personas.load_or_create(tmp_path, HOST)
    custom = make(tmp_path, settings=settings(hardware_concurrency=("custom", 3)))
    assert custom._resolve_persona().hardware_concurrency == 3
    assert personas.load(tmp_path).hardware_concurrency == seeded.hardware_concurrency
    mask = make(tmp_path, settings=settings())
    assert mask._resolve_persona().hardware_concurrency == seeded.hardware_concurrency


def test_without_settings_nothing_changes(tmp_path):
    eng = make(tmp_path, timezone="Asia/Tokyo", locale="ja-JP")
    persona = eng._resolve_persona()
    assert (persona.timezone, persona.locale) == ("Asia/Tokyo", "ja-JP")


def test_runner_hands_the_profile_settings_to_the_engine(tmp_path, monkeypatch):
    from chrome_engine import runner

    seen = {}

    class Stop(Exception):
        pass

    class Fake:
        def __init__(self, profile_dir, **kw):
            seen.update(kw)

        async def start(self):
            raise Stop

        async def stop(self):
            pass

    monkeypatch.setattr(runner, "ChromeEngine", Fake)
    monkeypatch.setattr(runner.fpsettings, "saved", lambda *a: ("saved", a))
    monkeypatch.setattr(runner, "ensure_installed", lambda: asyncio.sleep(0))
    asyncio.run(runner.run_browser("p", "None", "macos", "Asia/Tokyo", "ja-JP"))
    assert seen["settings"] == ("saved", ("p", "macos", "Asia/Tokyo", "ja-JP", "chrome"))
    assert "timezone" not in seen and "locale" not in seen


# --- Real browser ----------------------------------------------------------------------

browser = pytest.mark.browser


def run(coro, timeout=180):
    return asyncio.run(asyncio.wait_for(coro, timeout))


async def seen(chrome_exe, profile_dir, items=None, monkeypatch=None):
    """The probe's report for a profile launched with these settings."""
    eng = ChromeEngine(
        profile_dir,
        executable=chrome_exe,
        platform=HOST,
        headless=True,
        settings=settings(**(items or {})),
    )
    context = await eng.start()
    try:
        fp = await probe.collect(context)
        page = context.pages[0]
        async with probe.ProbeServer() as server:
            await page.goto(server.url + "/")
            fp["languages"] = await page.evaluate("navigator.languages")
            fp["acceptLanguage"] = await page.evaluate("fetch('/headers').then(r => r.json())")
        return eng, fp
    finally:
        await eng.stop()


@browser
def test_default_settings_keep_canvas_text_widths(chrome_exe, tmp_path):
    # Canvas noise would make measureText() return ~0 (fingerprint-chromium#96).
    async def widths():
        eng = ChromeEngine(
            tmp_path, executable=chrome_exe, platform=HOST, headless=True, settings=settings()
        )
        context = await eng.start()
        try:
            return await context.pages[0].evaluate(
                "() => { const c = document.createElement('canvas').getContext('2d');"
                " c.font = '16px Arial'; return c.measureText('Hello world').width; }"
            )
        finally:
            await eng.stop()

    assert run(widths()) > 40


@browser
def test_cores_timezone_and_language_reach_the_page(chrome_exe, tmp_path):
    eng, fp = run(
        seen(
            chrome_exe,
            tmp_path / "b",
            dict(
                hardware_concurrency=("custom", 3),
                timezone=("custom", "Asia/Tokyo"),
                language=("custom", "vi-VN"),
            ),
        )
    )
    assert fp["main"]["hardwareConcurrency"] == 3
    assert probe.same_timezone(fp["main"]["timezone"], "Asia/Tokyo")
    assert fp["languages"][0] == "vi-VN"
    assert probe.check(eng.persona, fp) == []


@browser
def test_audio_and_gpu_real_differ_from_noise(chrome_exe, tmp_path):
    # One profile dir with a fixed seed (noise can be too small to change a hash for
    # some seeds), so both launches have the same device.
    personas.save(tmp_path, personas.generate(HOST, seed=12345))
    _, real = run(seen(chrome_exe, tmp_path, dict(audio=("real",), webgl_meta=("real",))))
    _, noisy = run(seen(chrome_exe, tmp_path))
    assert real["audioHash"] != noisy["audioHash"]
    assert real["webgl"]["renderer"] != noisy["webgl"]["renderer"] or HOST != "macos"


@browser
def test_port_scan_is_blocked_by_default_and_open_when_real(chrome_exe, tmp_path):
    async def go(mode):
        from aiohttp import web

        hits = []

        async def handler(request):
            hits.append(request.path)
            return web.Response(text="x")

        async def ws(request):
            sock = web.WebSocketResponse()
            await sock.prepare(request)
            hits.append("ws")
            await sock.close()
            return sock

        app = web.Application()
        app.router.add_get("/ws", ws)
        app.router.add_get("/{p:.*}", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        eng = ChromeEngine(
            tmp_path / mode,
            executable=chrome_exe,
            platform=HOST,
            headless=True,
            settings=settings(port_scan=(mode,)),
        )
        context = await eng.start()
        try:
            await context.route(
                "https://public.example/**",
                lambda r: r.fulfill(body="<html></html>", content_type="text/html"),
            )
            page = context.pages[0]
            await page.goto("https://public.example/")
            got = await page.evaluate(
                """async (port) => ({
                    fetch: await fetch(`http://127.0.0.1:${port}/x`, {mode: 'no-cors'}).then(() => 'ok', () => 'blocked'),
                    ws: await new Promise((res) => {
                      const w = new WebSocket(`ws://localhost:${port}/ws`);
                      w.onopen = () => res('open'); w.onerror = () => res('error');
                      setTimeout(() => res('timeout'), 4000);
                    }),
                })""",
                port,
            )
        finally:
            await eng.stop()
            await runner.cleanup()
        return got, hits

    blocked, hits = run(go("mask"))
    assert blocked == {"fetch": "blocked", "ws": "error"} and hits == []
    opened, hits = run(go("real"))
    assert opened == {"fetch": "ok", "ws": "open"} and "ws" in hits
    # Back to mask in the same profile dir: the denial is written again.
    again, _ = run(go("mask"))
    assert again == {"fetch": "blocked", "ws": "error"}


@browser
def test_custom_geolocation_and_permissions(chrome_exe, tmp_path):
    pos = {"latitude": 35.68, "longitude": 139.69, "accuracy": 30}

    async def go(permission, geolocation=("custom", pos)):
        eng = ChromeEngine(
            tmp_path / permission,
            executable=chrome_exe,
            platform=HOST,
            headless=True,
            settings=settings(geo_permission=(permission,), geolocation=geolocation),
        )
        context = await eng.start()
        try:
            async with probe.ProbeServer() as server:
                page = context.pages[0]
                await page.goto(server.url + "/")
                return await page.evaluate(
                    """() => new Promise((res) => navigator.permissions.query({name: 'geolocation'}).then((p) => {
                        const state = p.state;  // live object: it changes once the request is answered
                        navigator.geolocation.getCurrentPosition(
                          (c) => res({state, lat: c.coords.latitude, lon: c.coords.longitude}),
                          (e) => res({state, error: e.code}), {timeout: 2500});
                    }))"""
                )
        finally:
            await eng.stop()

    allowed = run(go("allow"))
    assert allowed["state"] == "granted"
    assert (allowed["lat"], allowed["lon"]) == pytest.approx((35.68, 139.69))
    assert run(go("block"))["state"] == "denied"
    assert run(go("prompt"))["state"] == "prompt"


@browser
def test_mask_geolocation_without_a_fix_does_not_hand_out_the_real_position(
    chrome_exe, tmp_path, monkeypatch
):
    def offline(url):
        raise OSError("offline")

    monkeypatch.setattr(engine_mod, "lookup", offline)

    async def go():
        eng = ChromeEngine(
            tmp_path,
            executable=chrome_exe,
            platform=HOST,
            headless=True,
            settings=settings(geo_permission=("allow",)),
        )
        context = await eng.start()
        try:
            async with probe.ProbeServer() as server:
                page = context.pages[0]
                await page.goto(server.url + "/")
                state = await page.evaluate(
                    "navigator.permissions.query({name: 'geolocation'}).then((p) => p.state)"
                )
        finally:
            await eng.stop()
        return state, eng.warnings

    state, warnings = run(go())
    assert state == "prompt"
    assert any("not allowed" in w for w in warnings)


@browser
def test_geoip_behind_a_proxy_fills_only_the_masked_fields(chrome_exe, tmp_path, monkeypatch):
    from .servers import HttpProxy

    monkeypatch.setattr(
        engine_mod,
        "lookup",
        lambda url: ExitGeo(ip="203.0.113.7", timezone="Asia/Tokyo", locale="ja-JP"),
    )

    async def go():
        upstream = await HttpProxy().start()
        try:
            eng = ChromeEngine(
                tmp_path,
                executable=chrome_exe,
                platform=HOST,
                proxy=upstream.url,
                headless=True,
                settings=settings(language=("custom", "vi-VN")),  # timezone stays masked
            )
            await eng.start()
            await eng.stop()
            return eng
        finally:
            await upstream.stop()

    eng = run(go())
    assert (eng.persona.timezone, eng.persona.locale) == ("Asia/Tokyo", "vi-VN")
    prefs = json.loads((tmp_path / "Default" / "Preferences").read_text("utf-8"))
    assert prefs["webrtc"]["ip_handling_policy"] == fpmap.WEBRTC_PROXY
    assert re.fullmatch(r"\d+\.\d+\.\d+", eng.persona.platform_version)
