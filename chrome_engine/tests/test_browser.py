"""Integration tests against the real fingerprint-chromium build.

Skipped unless the pinned build is installed (python -m chrome_engine fetch).
Nothing here touches the internet: proxies, origins and the probe page are
local servers, and geo lookups are stubbed.
"""

from __future__ import annotations

import asyncio

import pytest

from chrome_engine import engine as engine_mod
from chrome_engine import probe
from chrome_engine.engine import ChromeEngine
from chrome_engine.geo import ExitGeo
from chrome_engine.persona import Persona
from chrome_engine.release import host_os

from .servers import HttpProxy, Origin, Socks5Proxy

pytestmark = pytest.mark.browser

HOST = host_os()
# Proxies would skip loopback targets without this, and every target here is local.
THROUGH_PROXY = ("--proxy-bypass-list=<-loopback>",)


def run(coro, timeout=120):
    return asyncio.run(asyncio.wait_for(coro, timeout))


def persona(seed=4242, platform=HOST, **kw):
    versions = {"windows": "19.0.0", "macos": "15.6.1", "linux": "6.8.0"}
    base = dict(
        seed=seed,
        platform=platform,
        platform_version=versions[platform],
        hardware_concurrency=8,
        timezone="Asia/Ho_Chi_Minh",
        locale="vi-VN",
    )
    return Persona(**{**base, **kw})


async def _probe(chrome_exe, profile_dir, **kwargs):
    eng = ChromeEngine(profile_dir, executable=chrome_exe, **kwargs)
    context = await eng.start()
    try:
        fp = await probe.collect(context)
        return eng, fp
    finally:
        await eng.stop()


@pytest.mark.parametrize("headless", [True, False, "offscreen"])
def test_fingerprint_is_coherent(chrome_exe, tmp_path, headless):
    p = persona()
    eng, fp = run(_probe(chrome_exe, tmp_path, persona=p, headless=headless))
    issues = probe.check(eng.persona, fp)
    assert issues == [], "\n".join(map(str, issues))
    assert probe.chrome_major(fp) == 148
    assert eng.crashes == []


@pytest.mark.parametrize("brand", ["Chrome", "Edge"])
def test_brands(chrome_exe, tmp_path, brand):
    p = persona(brand=brand, platform="windows" if HOST == "linux" else HOST)
    if HOST == "linux":
        pytest.skip("Edge personas are not offered on Linux")
    eng, fp = run(_probe(chrome_exe, tmp_path, persona=p, headless=True))
    assert probe.check(eng.persona, fp) == []


@pytest.mark.skipif(HOST != "windows", reason="cross-OS persona measured on Windows")
def test_macos_persona_on_windows_host(chrome_exe, tmp_path):
    p = persona(platform="macos")
    eng, fp = run(_probe(chrome_exe, tmp_path, persona=p, headless=True))
    assert probe.check(eng.persona, fp) == []
    assert "Apple" in fp["webgl"]["renderer"]
    assert eng.warnings  # fonts are still the host's


def test_emoji_canvas_does_not_crash(chrome_exe, tmp_path):
    """150.0.7871.186 crashed here in ~50% of launches; the pin must not."""

    async def go():
        for seed in range(1000, 1006):
            eng = ChromeEngine(
                tmp_path / str(seed),
                executable=chrome_exe,
                persona=persona(seed=seed),
                headless=True,
            )
            context = await eng.start()
            try:
                async with probe.ProbeServer() as server:
                    page = context.pages[0]
                    await page.goto(server.url + "/")
                    assert await page.evaluate(probe.EMOJI_CANVAS_JS) > 0
                    assert await page.evaluate(probe.EMOJI_CANVAS_JS) > 0
                assert eng.crashes == []
            finally:
                await eng.stop()

    run(go(), timeout=300)


def test_same_seed_same_device_across_launches(chrome_exe, tmp_path):
    p = persona(seed=777)
    _, a = run(_probe(chrome_exe, tmp_path / "a", persona=p, headless=True))
    _, b = run(_probe(chrome_exe, tmp_path / "b", persona=p, headless=True))
    assert a["canvasHash"] == b["canvasHash"]
    assert a["audioHash"] == b["audioHash"]
    assert a["webgl"] == b["webgl"]


def test_different_seeds_are_different_devices(chrome_exe, tmp_path):
    _, a = run(_probe(chrome_exe, tmp_path / "a", persona=persona(seed=101), headless=True))
    _, b = run(_probe(chrome_exe, tmp_path / "b", persona=persona(seed=202), headless=True))
    assert a["canvasHash"] != b["canvasHash"]
    assert a["audioHash"] != b["audioHash"]


def test_profile_persists_cookies_storage_and_persona(chrome_exe, tmp_path):
    async def go():
        origin = await Origin("localhost").start()
        try:
            eng = ChromeEngine(tmp_path, executable=chrome_exe, headless=True)
            context = await eng.start()
            first = eng.persona
            page = context.pages[0]
            await page.goto(origin.url + "/")
            await page.evaluate(
                "() => { document.cookie = 'sid=abc; max-age=86400'; localStorage.setItem('k', 'v'); }"
            )
            await eng.stop()

            eng = ChromeEngine(tmp_path, executable=chrome_exe, headless=True)
            context = await eng.start()
            try:
                page = context.pages[0]
                await page.goto(origin.url + "/")
                cookie, stored = await page.evaluate(
                    "() => [document.cookie, localStorage.getItem('k')]"
                )
                assert "sid=abc" in cookie
                assert stored == "v"
                assert eng.persona == first
            finally:
                await eng.stop()
        finally:
            await origin.stop()

    run(go())


@pytest.mark.parametrize("proxy_cls", [HttpProxy, Socks5Proxy])
def test_authenticated_proxy(chrome_exe, tmp_path, proxy_cls):
    async def go():
        origin = await Origin("localhost").start()
        upstream = await proxy_cls().start()
        try:
            eng = ChromeEngine(
                tmp_path,
                executable=chrome_exe,
                persona=persona(),
                proxy=upstream.url,
                headless=True,
                extra_args=THROUGH_PROXY,
            )
            context = await eng.start()
            try:
                page = context.pages[0]
                await page.goto(origin.url + "/")
                assert "origin-ok" in await page.content()
                fp = await probe.collect(context)
            finally:
                await eng.stop()
            issues = probe.check(eng.persona, fp)
            assert issues == [], "\n".join(map(str, issues))
            assert fp["webrtcCandidates"] == []
            if isinstance(upstream, Socks5Proxy):
                # Names reach the proxy unresolved: no DNS leak.
                assert ("domain", "localhost", origin.port) in upstream.targets
            else:
                assert any(target.startswith("http://localhost") for _, target in upstream.requests)
            assert origin.hits
        finally:
            await upstream.stop()
            await origin.stop()

    run(go())


def test_wrong_proxy_credentials_never_fall_back_to_direct(chrome_exe, tmp_path):
    async def go():
        origin = await Origin("localhost").start()
        upstream = await HttpProxy(password="right").start()
        try:
            bad = upstream.url.replace("right", "wrong")
            eng = ChromeEngine(
                tmp_path,
                executable=chrome_exe,
                persona=persona(),
                proxy=bad,
                headless=True,
                extra_args=THROUGH_PROXY,
            )
            context = await eng.start()
            try:
                with pytest.raises(Exception):  # noqa: B017 - any navigation error
                    await context.pages[0].goto(origin.url + "/", timeout=15_000)
            finally:
                await eng.stop()
            assert origin.hits == []
            assert upstream.rejected >= 1
        finally:
            await upstream.stop()
            await origin.stop()

    run(go())


def test_geoip_fills_timezone_locale_and_position(chrome_exe, tmp_path, monkeypatch):
    seen = []

    def fake_lookup(url):
        seen.append(url)
        return ExitGeo(
            ip="203.0.113.7",
            timezone="Asia/Tokyo",
            locale="ja-JP",
            latitude=35.68,
            longitude=139.69,
        )

    monkeypatch.setattr(engine_mod, "lookup", fake_lookup)

    async def go():
        upstream = await HttpProxy().start()
        try:
            p = persona(timezone=None, locale=None)
            eng = ChromeEngine(
                tmp_path, executable=chrome_exe, persona=p, proxy=upstream.url, headless=True
            )
            context = await eng.start()
            try:
                await context.grant_permissions(["geolocation"])
                fp = await probe.collect(context)
                async with probe.ProbeServer() as server:
                    page = context.pages[0]
                    await page.goto(server.url + "/")
                    coords = await page.evaluate(
                        """() => new Promise((ok, fail) => navigator.geolocation.getCurrentPosition(
                            p => ok([p.coords.latitude, p.coords.longitude]), fail))"""
                    )
            finally:
                await eng.stop()
            assert seen and seen[0].startswith("http://127.0.0.1:")  # through the bridge
            assert (eng.persona.timezone, eng.persona.locale) == ("Asia/Tokyo", "ja-JP")
            assert probe.check(eng.persona, fp) == []
            assert coords == pytest.approx([35.68, 139.69])
        finally:
            await upstream.stop()

    run(go())


def test_saved_persona_does_not_store_geo(chrome_exe, tmp_path, monkeypatch):
    monkeypatch.setattr(
        engine_mod,
        "lookup",
        lambda url: ExitGeo(ip="203.0.113.7", timezone="Asia/Tokyo", locale="ja-JP"),
    )

    async def go():
        upstream = await HttpProxy().start()
        try:
            eng = ChromeEngine(tmp_path, executable=chrome_exe, proxy=upstream.url, headless=True)
            await eng.start()
            await eng.stop()
        finally:
            await upstream.stop()

    run(go())
    from chrome_engine.persona import load

    saved = load(tmp_path)
    # The next launch may use another exit IP: geo must not be frozen into the persona.
    assert (saved.timezone, saved.locale) == (None, None)


def test_automation_switches_are_gone(chrome_exe, tmp_path):
    async def go():
        eng = ChromeEngine(tmp_path, executable=chrome_exe, persona=persona(), headless=True)
        context = await eng.start()
        try:
            page = context.pages[0]
            await page.goto("chrome://version")
            return await page.inner_text("#command_line")
        finally:
            await eng.stop()

    cmdline = run(go())
    for switch in engine_mod.IGNORED_DEFAULT_ARGS:
        assert f"{switch} " not in cmdline + " ", switch
    # Playwright's feature list (storage partitioning off, HTTPS upgrades off...) is gone.
    assert "--disable-features=" not in cmdline
    assert "ThirdPartyStoragePartitioning" not in cmdline


def test_popups_are_blocked_like_a_normal_browser(chrome_exe, tmp_path):
    async def go():
        eng = ChromeEngine(tmp_path, executable=chrome_exe, persona=persona(), headless=True)
        context = await eng.start()
        try:
            page = context.pages[0]
            # An inline script has no user gesture (page.evaluate would have one),
            # so Chrome's popup blocker must refuse the window.
            html = "<script>document.title = String(window.open('about:blank') === null)</script>"
            await page.goto("data:text/html," + html)
            await page.wait_for_function("() => document.title !== ''")
            return await page.title(), len(context.pages)
        finally:
            await eng.stop()

    assert run(go()) == ("true", 1)


def test_third_party_storage_is_partitioned(chrome_exe, tmp_path):
    """Playwright turns partitioning off; the engine must turn it back on."""

    async def go():
        top = await Origin("127.0.0.1").start()
        third = await Origin("localhost").start()
        eng = ChromeEngine(tmp_path, executable=chrome_exe, persona=persona(), headless=True)
        context = await eng.start()
        try:
            page = context.pages[0]
            await page.goto(third.url + "/")
            await page.evaluate("() => localStorage.setItem('k', 'first-party')")
            await page.goto(top.url + "/")
            await page.evaluate(
                """(src) => new Promise(r => { const f = document.createElement('iframe');
                   f.src = src; f.onload = r; document.body.appendChild(f); })""",
                third.url + "/",
            )
            frame = next(f for f in page.frames if f.url.startswith(third.url))
            return await frame.evaluate("() => localStorage.getItem('k')")
        finally:
            await eng.stop()
            await top.stop()
            await third.stop()

    assert run(go()) is None


def test_runtime_enable_is_not_visible(chrome_exe, tmp_path):
    _, fp = run(_probe(chrome_exe, tmp_path, persona=persona(), headless=True))
    assert fp["cdpDetected"] is False
    assert fp["main"]["webdriver"] is False


def test_webrtc_policy_follows_the_proxy(chrome_exe, tmp_path):
    """Direct: public interface only (never a LAN address). Proxied: no UDP at all."""
    import json

    def policy(profile):
        prefs = json.loads((profile / "Default" / "Preferences").read_text("utf-8"))
        return prefs["webrtc"]["ip_handling_policy"]

    async def go():
        eng = ChromeEngine(tmp_path, executable=chrome_exe, persona=persona(), headless=True)
        context = await eng.start()
        try:
            fp = await probe.collect(context)
        finally:
            await eng.stop()
        assert probe.check(eng.persona, fp) == []
        assert policy(tmp_path) == engine_mod.WEBRTC_POLICY_DIRECT

        upstream = await HttpProxy().start()
        try:
            eng = ChromeEngine(
                tmp_path,
                executable=chrome_exe,
                persona=persona(),
                proxy=upstream.url,
                headless=True,
            )
            await eng.start()
            await eng.stop()
        finally:
            await upstream.stop()
        assert policy(tmp_path) == engine_mod.WEBRTC_POLICY_PROXY

    run(go())


def test_parallel_profiles_are_isolated(chrome_exe, tmp_path):
    """Three profiles at once: separate devices, separate cookies."""

    async def one(i, origin):
        p = persona(seed=5000 + i, hardware_concurrency=4 * (i + 1))
        eng = ChromeEngine(tmp_path / f"p{i}", executable=chrome_exe, persona=p, headless=True)
        context = await eng.start()
        try:
            page = context.pages[0]
            await page.goto(origin.url + "/")
            await page.evaluate(f"() => {{ document.cookie = 'who={i}; max-age=600'; }}")
            fp = await probe.collect(context)
            await page.goto(origin.url + "/")
            cookie = await page.evaluate("() => document.cookie")
            return eng.persona, fp, cookie
        finally:
            await eng.stop()

    async def go():
        origin = await Origin("localhost").start()
        try:
            return await asyncio.gather(*(one(i, origin) for i in range(3)))
        finally:
            await origin.stop()

    results = run(go(), timeout=180)
    for i, (p, fp, cookie) in enumerate(results):
        assert probe.check(p, fp) == []
        assert cookie == f"who={i}"
        assert fp["main"]["hardwareConcurrency"] == 4 * (i + 1)
    assert len({fp["canvasHash"] for _, fp, _ in results}) == 3
