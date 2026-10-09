"""Read back what a running profile shows to websites, and check it is coherent.

`collect()` serves a probe page on loopback, opens it in the profile and reads
the values fingerprinting scripts look at, from the window, a dedicated worker
and an iframe, together with the request headers the page was loaded with.
`check()` compares that against the persona and reports every mismatch:
detectors rarely flag a single value, they flag values that disagree.
"""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Any

from aiohttp import web

from .persona import Persona

_IDENTITY_JS = r"""
() => ({
  userAgent: navigator.userAgent,
  platform: navigator.platform,
  languages: navigator.languages,
  hardwareConcurrency: navigator.hardwareConcurrency,
  deviceMemory: navigator.deviceMemory ?? null,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  webdriver: navigator.webdriver,
})
"""

_PROBE_JS = r"""
async () => {
  const IDENTITY = %IDENTITY%;
  const identity = eval('(' + IDENTITY + ')()');
  const hash = async (s) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))]
    .map(b => b.toString(16).padStart(2, '0')).join('');

  const workerSrc = 'postMessage((' + IDENTITY + ')());';
  const worker = await new Promise((resolve) => {
    const w = new Worker(URL.createObjectURL(new Blob([workerSrc], {type: 'text/javascript'})));
    w.onmessage = (e) => resolve(e.data);
    w.onerror = (e) => resolve({error: String(e.message)});
    setTimeout(() => resolve({error: 'timeout'}), 5000);
  });

  const iframe = await new Promise((resolve) => {
    const f = document.createElement('iframe');
    f.src = '/blank';
    f.onload = () => resolve(f.contentWindow.eval('(' + IDENTITY + ')()'));
    document.body.appendChild(f);
    setTimeout(() => resolve({error: 'timeout'}), 5000);
  });

  // CreepJS and others read the device again from service and shared workers.
  const serviceWorker = await (async () => {
    try {
      const reg = await navigator.serviceWorker.register('/sw.js');
      await navigator.serviceWorker.ready;
      return await new Promise((resolve) => {
        navigator.serviceWorker.onmessage = (e) => resolve(e.data);
        (reg.active || reg.waiting || reg.installing).postMessage('probe');
        setTimeout(() => resolve({error: 'timeout'}), 5000);
      });
    } catch (e) { return {error: String(e)}; }
  })();

  const sharedWorker = await new Promise((resolve) => {
    try {
      const w = new SharedWorker('/shared.js');
      w.port.onmessage = (e) => resolve(e.data);
      w.port.start();
    } catch (e) { resolve({error: String(e)}); }
    setTimeout(() => resolve({error: 'timeout'}), 5000);
  });

  const canvas = document.createElement('canvas');
  canvas.width = 240; canvas.height = 60;
  const ctx = canvas.getContext('2d');
  ctx.textBaseline = 'top'; ctx.font = '16px Arial';
  ctx.fillStyle = '#f60'; ctx.fillRect(100, 1, 62, 20);
  ctx.fillStyle = '#069'; ctx.fillText('FoxProfile, probe <canvas> 1.0', 2, 15);
  ctx.fillStyle = 'rgba(102, 204, 0, 0.7)'; ctx.fillText('FoxProfile, probe <canvas> 1.0', 4, 17);
  const canvasHash = await hash(canvas.toDataURL());

  let webgl = null;
  try {
    const gl = document.createElement('canvas').getContext('webgl');
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    webgl = {
      vendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
      renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
      extensions: gl.getSupportedExtensions().length,
    };
  } catch (e) { webgl = {error: String(e)}; }

  let audioHash = null;
  try {
    const ac = new OfflineAudioContext(1, 5000, 44100);
    const osc = ac.createOscillator(); osc.type = 'triangle'; osc.frequency.value = 10000;
    const comp = ac.createDynamicsCompressor();
    osc.connect(comp); comp.connect(ac.destination); osc.start(0);
    const buf = await ac.startRendering();
    audioHash = await hash(Array.from(buf.getChannelData(0).slice(4500)).join(','));
  } catch (e) { audioHash = 'error: ' + e; }

  // console.debug serialises the error's stack only when a DevTools client has
  // called Runtime.enable: the classic CDP detection.
  let cdpDetected = false;
  const err = new Error();
  Object.defineProperty(err, 'stack', { get() { cdpDetected = true; return ''; } });
  console.debug(err);

  const candidates = await new Promise((resolve) => {
    const out = [];
    try {
      const pc = new RTCPeerConnection({iceServers: []});
      pc.createDataChannel('probe');
      pc.onicecandidate = (e) => { if (!e.candidate) resolve(out); else out.push(e.candidate.candidate); };
      pc.createOffer().then((o) => pc.setLocalDescription(o));
    } catch (e) { resolve(['error: ' + e]); }
    setTimeout(() => resolve(out), 3000);
  });

  let uaData = null;
  if (navigator.userAgentData) {
    uaData = await navigator.userAgentData.getHighEntropyValues(
      ['platform', 'platformVersion', 'architecture', 'bitness', 'model', 'fullVersionList']);
  }

  return {
    main: identity, worker, iframe, serviceWorker, sharedWorker, uaData, canvasHash, audioHash, webgl, cdpDetected,
    webrtcCandidates: candidates,
    screen: {width: screen.width, height: screen.height, availWidth: screen.availWidth,
             availHeight: screen.availHeight, colorDepth: screen.colorDepth, dpr: devicePixelRatio},
    window: {outerWidth, outerHeight, innerWidth, innerHeight},
    scrollbarWidth: (() => {
      const d = document.createElement('div');
      d.style.cssText = 'width:100px;height:100px;overflow:scroll;position:absolute;top:-999px';
      document.body.appendChild(d);
      const w = d.offsetWidth - d.clientWidth;
      d.remove();
      return w;
    })(),
    plugins: navigator.plugins.length,
    maxTouchPoints: navigator.maxTouchPoints,
    chrome: typeof window.chrome,
    timezoneOffset: new Date().getTimezoneOffset(),
  };
}
""".replace("%IDENTITY%", json.dumps(_IDENTITY_JS.strip()))

_SERVICE_WORKER_JS = (
    "self.addEventListener('message', (e) => e.source.postMessage(("
    + _IDENTITY_JS.strip()
    + ")()));"
)
_SHARED_WORKER_JS = "onconnect = (e) => e.ports[0].postMessage((" + _IDENTITY_JS.strip() + ")());"

EMOJI_CANVAS_JS = r"""
() => {
  const c = document.createElement('canvas');
  const x = c.getContext('2d');
  x.font = '18px Arial';
  x.fillText('probe \u{1F600} \u{1F389}', 2, 20);
  return c.toDataURL().length;
}
"""


class ProbeServer:
    """Serves the probe page on 127.0.0.1 and records each request's headers."""

    def __init__(self) -> None:
        self.headers: dict[str, dict[str, str]] = {}
        self.port = 0
        self._runner: web.AppRunner | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> ProbeServer:
        app = web.Application()
        app.router.add_get("/", self._page)
        app.router.add_get("/blank", self._page)
        app.router.add_get("/headers", self._dump)
        app.router.add_get("/sw.js", self._script(_SERVICE_WORKER_JS))
        app.router.add_get("/shared.js", self._script(_SHARED_WORKER_JS))
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def __aenter__(self) -> ProbeServer:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    @staticmethod
    def _script(source: str):
        async def handler(request: web.Request) -> web.Response:
            return web.Response(text=source, content_type="text/javascript")

        return handler

    async def _page(self, request: web.Request) -> web.Response:
        self.headers[request.path] = {k.lower(): v for k, v in request.headers.items()}
        body = (
            "<!doctype html><html><head><title>probe</title></head><body><p>probe</p></body></html>"
        )
        return web.Response(text=body, content_type="text/html")

    async def _dump(self, request: web.Request) -> web.Response:
        return web.json_response(self.headers)


async def collect(context: Any, page: Any = None) -> dict[str, Any]:
    """Everything `check` needs, read from a page of `context`."""
    async with ProbeServer() as server:
        own_page = page is None
        page = page or await context.new_page()
        try:
            await page.goto(server.url + "/", wait_until="load")
            result = await page.evaluate(_PROBE_JS)
        finally:
            if own_page:
                await page.close()
        result["headers"] = server.headers.get("/", {})
        return result


@dataclass(frozen=True)
class Issue:
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


_UA_OS = {"windows": "Windows NT", "macos": "Macintosh", "linux": "X11; Linux"}
_NAV_PLATFORM = {"windows": "Win32", "macos": "MacIntel", "linux": "Linux x86_64"}
_CH_PLATFORM = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}
_BRAND = {"Chrome": "Google Chrome", "Edge": "Microsoft Edge"}
_IDENTITY_KEYS = ("userAgent", "platform", "languages", "hardwareConcurrency", "timezone")


def same_timezone(a: str, b: str) -> bool:
    """True when two IANA names are the same zone (Chrome reports Asia/Saigon
    for Asia/Ho_Chi_Minh: ICU keeps the older canonical names)."""
    if a == b:
        return True
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        za, zb = ZoneInfo(a), ZoneInfo(b)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    year = datetime.now(timezone.utc).year
    samples = [
        datetime(y, m, 15, 12, tzinfo=timezone.utc) for y in (year - 1, year) for m in (1, 4, 7, 10)
    ]
    return all(s.astimezone(za).utcoffset() == s.astimezone(zb).utcoffset() for s in samples)


def _offset_minutes(name: str) -> int:
    """JavaScript's getTimezoneOffset() for `name` right now (minutes, west positive)."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    offset = datetime.now(timezone.utc).astimezone(ZoneInfo(name)).utcoffset()
    return -int(offset.total_seconds() // 60) if offset is not None else 0


def _webgl_matches(platform: str, renderer: str) -> bool:
    r = renderer.lower()
    if platform == "windows":
        return "direct3d" in r or "d3d" in r
    if platform == "macos":
        return "metal" in r or "apple" in r or "opengl" in r
    return "direct3d" not in r and "d3d11" not in r and "metal" not in r


def _private_ip_candidates(candidates: list[str]) -> list[str]:
    leaks = []
    for candidate in candidates:
        for token in candidate.split():
            try:
                ip = ipaddress.ip_address(token)
            except ValueError:
                continue
            if not ip.is_loopback:
                leaks.append(str(ip))
    return leaks


def check(persona: Persona, fp: dict[str, Any]) -> list[Issue]:
    """Every way `fp` (from collect) disagrees with `persona` or with itself."""
    issues: list[Issue] = []

    def expect(ok: bool, code: str, detail: str) -> None:
        if not ok:
            issues.append(Issue(code, detail))

    main = fp.get("main") or {}
    ua = main.get("userAgent", "")
    expect(
        _UA_OS[persona.platform] in ua, "ua_os", f"User-Agent does not say {persona.platform}: {ua}"
    )
    expect("HeadlessChrome" not in ua, "ua_headless", "User-Agent says HeadlessChrome")
    expect(
        main.get("platform") == _NAV_PLATFORM[persona.platform],
        "navigator_platform",
        f"navigator.platform is {main.get('platform')!r}",
    )
    expect(
        main.get("hardwareConcurrency") == persona.hardware_concurrency,
        "hardware_concurrency",
        f"{main.get('hardwareConcurrency')} cores, persona has {persona.hardware_concurrency}",
    )
    expect(
        main.get("webdriver") is False,
        "webdriver",
        f"navigator.webdriver is {main.get('webdriver')!r}",
    )
    if persona.timezone:
        expect(
            same_timezone(main.get("timezone") or "", persona.timezone),
            "timezone",
            f"timezone is {main.get('timezone')}, persona has {persona.timezone}",
        )
        expected_offset = _offset_minutes(persona.timezone)
        expect(
            fp.get("timezoneOffset") == expected_offset,
            "timezone_offset",
            f"Date offset is {fp.get('timezoneOffset')}, {persona.timezone} is {expected_offset}",
        )
    if persona.locale:
        langs = main.get("languages") or []
        expect(
            bool(langs) and langs[0] == persona.locale,
            "language",
            f"navigator.languages is {langs}, persona has {persona.locale}",
        )

    for realm in ("worker", "iframe", "serviceWorker", "sharedWorker"):
        other = fp.get(realm) or {}
        if "error" in other:
            issues.append(Issue(f"{realm}_error", other["error"]))
            continue
        for key in _IDENTITY_KEYS:
            expect(
                other.get(key) == main.get(key),
                f"{realm}_{key}",
                f"{realm} reports {other.get(key)!r}, window reports {main.get(key)!r}",
            )

    ua_data = fp.get("uaData") or {}
    expect(
        ua_data.get("platform") == _CH_PLATFORM[persona.platform],
        "uadata_platform",
        f"userAgentData.platform is {ua_data.get('platform')!r}",
    )
    expect(
        ua_data.get("platformVersion") == persona.platform_version,
        "uadata_platform_version",
        f"platformVersion is {ua_data.get('platformVersion')!r}, persona has {persona.platform_version}",
    )
    brands = [b.get("brand") for b in ua_data.get("brands") or []]
    expect(_BRAND[persona.brand] in brands, "brand", f"brands are {brands}")

    headers = fp.get("headers") or {}
    expect(
        headers.get("user-agent") == ua,
        "header_user_agent",
        "the User-Agent header differs from navigator.userAgent",
    )
    expect(
        headers.get("sec-ch-ua-platform") == json.dumps(_CH_PLATFORM[persona.platform]),
        "header_platform",
        f"Sec-CH-UA-Platform is {headers.get('sec-ch-ua-platform')!r}",
    )
    expect(
        _BRAND[persona.brand] in headers.get("sec-ch-ua", ""),
        "header_brand",
        f"Sec-CH-UA is {headers.get('sec-ch-ua')!r}",
    )
    if persona.locale:
        expect(
            headers.get("accept-language", "").startswith(persona.locale),
            "header_language",
            f"Accept-Language is {headers.get('accept-language')!r}",
        )

    webgl = fp.get("webgl") or {}
    if "renderer" in webgl:
        expect(
            _webgl_matches(persona.platform, webgl["renderer"]),
            "webgl_renderer",
            f"WebGL renderer {webgl['renderer']!r} does not fit {persona.platform}",
        )
    else:
        issues.append(Issue("webgl_unavailable", str(webgl.get("error"))))

    expect(
        not fp.get("cdpDetected"), "cdp_runtime", "a DevTools client is visible (Runtime.enable)"
    )

    leaks = _private_ip_candidates(fp.get("webrtcCandidates") or [])
    expect(not leaks, "webrtc_ip", f"WebRTC exposes {leaks}")

    screen = fp.get("screen") or {}
    window = fp.get("window") or {}
    expect(
        (screen.get("width"), screen.get("height")) != (800, 600),
        "screen_default",
        "screen is 800x600 (headless default)",
    )
    expect(
        screen.get("width", 0) >= window.get("innerWidth", 0),
        "screen_window",
        f"window ({window.get('innerWidth')}) is wider than the screen ({screen.get('width')})",
    )
    if persona.platform != "macos":
        # macOS may hide scrollbars (overlay); Windows and Linux never do, but
        # headless Chrome with --hide-scrollbars reports 0.
        expect(
            (fp.get("scrollbarWidth") or 0) > 0,
            "scrollbar_width",
            f"scrollbars are {fp.get('scrollbarWidth')}px wide",
        )
    return issues


_VERSION_IN_UA = re.compile(r"Chrome/(\d+)")


def chrome_major(fp: dict[str, Any]) -> int | None:
    match = _VERSION_IN_UA.search((fp.get("main") or {}).get("userAgent", ""))
    return int(match.group(1)) if match else None
