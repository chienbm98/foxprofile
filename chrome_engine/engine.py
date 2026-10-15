"""Launch a fingerprint-chromium profile as a Playwright BrowserContext.

    async with ChromeEngine("data/alice", proxy="socks5://u:p@host:1080") as context:
        page = context.pages[0]
        await page.goto("https://example.com")

What the engine adds on top of a bare `launch_persistent_context`:

- a persistent persona (seed, OS, brand, cores) per profile directory;
- proxies with credentials, through a loopback bridge (proxy_bridge.py);
- timezone / locale from the proxy's exit IP unless the persona pins them;
- Playwright's automation switches removed where a page can observe them;
- a refusal to present an OS the host cannot fake consistently.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import fetch
from . import persona as personas
from . import settings as fpmap
from .geo import ExitGeo, lookup
from .proxy_bridge import ProxyBridge, Upstream
from .release import host_os

# Playwright defaults a page can observe, or that make the browser behave
# unlike a person's Chrome. Everything else Playwright passes is kept, except
# its --disable-features list (see playwright_disabled_features_arg).
IGNORED_DEFAULT_ARGS = (
    "--enable-automation",
    "--disable-popup-blocking",
    "--disable-extensions",
    "--disable-component-extensions-with-background-pages",
    "--disable-default-apps",
    "--disable-back-forward-cache",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-ipc-flooding-protection",
    "--force-color-profile=srgb",
    "--hide-scrollbars",
    "--disable-sync",
    "--no-sandbox",
)
HEADLESS_SCREEN = (1920, 1080)

_FEATURES_BLOCK = re.compile(r"disabledFeatures = \[(.*?)\]\.filter\(Boolean\)", re.S)


@functools.lru_cache(maxsize=1)
def playwright_disabled_features_arg() -> str | None:
    """Playwright's own --disable-features switch, exactly as it passes it.

    It turns off third-party storage partitioning, HTTPS upgrades, paint
    holding and more, and ignore_default_args only drops exact matches, so the
    string is read from the installed Playwright driver. None when it cannot be
    reproduced; test_browser.py::test_automation_switches_are_gone notices.
    """
    try:
        from playwright._impl._driver import compute_driver_executable

        driver = compute_driver_executable()
        cli = Path(driver[-1] if isinstance(driver, tuple) else driver)
        lib = cli.parent / "lib"
        for path in (lib / "coreBundle.js", lib / "server" / "chromium" / "chromiumSwitches.js"):
            if not path.is_file():
                continue
            match = _FEATURES_BLOCK.search(path.read_text(encoding="utf-8", errors="replace"))
            if not match:
                continue
            body = re.sub(r"//[^\n]*", "", match.group(1))
            if "?" in body:  # an entry depends on the environment
                return None
            return "--disable-features=" + ",".join(re.findall(r'"([^"]+)"', body))
    except Exception:
        return None
    return None


# fingerprint-chromium ignores Chrome's --force-webrtc-ip-handling-policy and it
# does not hide LAN addresses behind mDNS names, so the policy is set through
# the profile's preferences on every launch:
# - behind a proxy, no UDP at all: no candidate can reveal the real IP;
# - without one, only the public address (the one sites already see) and never
#   a LAN address. Fully blocked WebRTC is itself unusual.
WEBRTC_POLICY_PROXY = fpmap.WEBRTC_PROXY
WEBRTC_POLICY_DIRECT = fpmap.WEBRTC_DIRECT


def set_prefs(profile_dir: Path, updates: dict[str, object]) -> None:
    """Write dotted preference paths ("webrtc.ip_handling_policy") into the profile's
    Default/Preferences; a None value removes the key. Rewrites only on a change."""
    path = profile_dir / "Default" / "Preferences"
    try:
        prefs = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(prefs, dict):
            prefs = {}
    except (OSError, ValueError):
        prefs = {}
    changed = False
    for dotted, new in updates.items():
        *parents, leaf = dotted.split(".")
        node = prefs
        for key in parents:
            child = node.get(key)
            if not isinstance(child, dict):
                if new is None:
                    break
                child = node[key] = {}
            node = child
        else:
            if new is None:
                changed |= node.pop(leaf, None) is not None
            elif node.get(leaf) != new:
                node[leaf] = new
                changed = True
    if not changed:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("Preferences.foxprofile-tmp")
    tmp.write_text(json.dumps(prefs), encoding="utf-8")
    tmp.replace(path)


def set_webrtc_policy(profile_dir: Path, policy: str) -> None:
    set_prefs(profile_dir, {"webrtc.ip_handling_policy": policy})


class EngineError(RuntimeError):
    pass


class EngineNotInstalled(EngineError):
    pass


def default_sandbox() -> bool:
    # Chromium refuses to run sandboxed as root on Linux.
    if sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0:
        return False
    return True


def build_args(
    persona: personas.Persona,
    proxy_url: str | None = None,
    headless: bool | str = False,
    extra_args: tuple[str, ...] | list[str] = (),
) -> list[str]:
    """Command-line switches for a launch (Playwright adds its own before these)."""
    args = persona.to_args()
    if proxy_url:
        args.append(f"--proxy-server={proxy_url}")
    args += ["--no-first-run", "--no-default-browser-check", "--hide-crash-restore-bubble"]
    if headless is True:
        # Headless otherwise reports an 800x600 screen.
        w, h = HEADLESS_SCREEN
        args += [f"--window-size={w},{h}", f"--screen-info={{0,0 {w}x{h}}}"]
    elif headless == "offscreen":
        args += ["--window-position=-32000,-32000", "--window-size=1600,900"]
    else:
        args.append("--start-maximized")
    args += list(extra_args)
    return args


class ChromeEngine:
    """One running fingerprint-chromium profile. Use as an async context manager."""

    def __init__(
        self,
        profile_dir: str | Path,
        *,
        platform: str | None = None,
        persona: personas.Persona | None = None,
        proxy: str | None = None,
        headless: bool | str = False,
        geoip: bool = True,
        timezone: str | None = None,
        locale: str | None = None,
        executable: str | Path | None = None,
        version: str | None = None,
        extra_args: tuple[str, ...] | list[str] = (),
        allow_unsupported: bool = False,
        sandbox: bool | None = None,
        settings: dict | None = None,
    ) -> None:
        if headless not in (True, False, "offscreen"):
            raise ValueError("headless must be True, False or 'offscreen'")
        self.profile_dir = Path(profile_dir)
        self._platform = platform
        self._persona = persona
        self._proxy = proxy
        self.headless = headless
        self.geoip = geoip
        self._timezone = timezone
        self._locale = locale
        self._executable = executable
        self._version = version
        self._extra_args = tuple(extra_args)
        # FoxProfile's fingerprint settings (see settings.py). When given they decide
        # cores, timezone, language, WebRTC, geolocation etc. and win over `timezone`,
        # `locale` and the saved persona; nothing of them is written to the persona file.
        self._plan = fpmap.plan(settings, os.cpu_count() or 8) if settings is not None else None
        self._allow_unsupported = allow_unsupported
        self.sandbox = default_sandbox() if sandbox is None else sandbox

        self.persona: personas.Persona | None = None
        self.geo: ExitGeo | None = None
        self.bridge: ProxyBridge | None = None
        self.args: list[str] = []
        self.warnings: list[str] = []
        self.crashes: list[str] = []
        self.context: Any = None
        self._playwright: Any = None

    # --- lifecycle --------------------------------------------------------

    async def __aenter__(self) -> Any:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    async def start(self) -> Any:
        if self.context is not None or self.bridge is not None:
            raise EngineError("The engine is already running; stop() it first")
        try:
            return await self._start()
        except BaseException:
            await self.stop()
            raise

    async def _start(self) -> Any:
        executable = self._resolve_executable()
        persona = self._resolve_persona()
        plan = self._plan

        upstream = Upstream.parse(self._proxy) if self._proxy else None
        if upstream:
            self.bridge = await ProxyBridge(upstream).start()

        if plan is None:
            if upstream and self.geoip and not (persona.timezone and persona.locale):
                self.geo = await self._lookup_geo()
                persona = persona.with_geo(self.geo.timezone, self.geo.locale)
        elif plan.follow and self.geoip and (upstream or self._needs_own_position(plan)):
            # Behind a proxy the exit IP places everything that follows it. Without
            # one only the position needs the lookup: the host's own timezone and
            # language are already right for its IP.
            try:
                self.geo = await self._lookup_geo()
            except EngineError:
                if upstream:
                    raise
                self.warnings.append("Could not place this machine's IP; geolocation is not masked")
            else:
                if upstream:
                    persona = replace(
                        persona,
                        timezone=self.geo.timezone
                        if "timezone" in plan.follow
                        else persona.timezone,
                        locale=self.geo.locale if "locale" in plan.follow else persona.locale,
                    )
        self.persona = persona

        self.args = build_args(
            persona,
            proxy_url=self.bridge.url if self.bridge else None,
            headless=self.headless,
            extra_args=[*self._extra_args, *(plan.args() if plan else ())],
        )

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        if plan is None:
            set_webrtc_policy(
                self.profile_dir, WEBRTC_POLICY_PROXY if self.bridge else WEBRTC_POLICY_DIRECT
            )
        else:
            set_prefs(self.profile_dir, plan.prefs(proxied=self.bridge is not None))
        self.context = await self._playwright.chromium.launch_persistent_context(
            str(self.profile_dir),
            executable_path=str(executable),
            headless=self.headless is True,
            args=self.args,
            ignore_default_args=self._ignored_default_args(),
            no_viewport=True,
            chromium_sandbox=self.sandbox,
            accept_downloads=True,
        )
        await self._apply_geolocation()
        for page in self.context.pages:
            self._watch(page)
        self.context.on("page", self._watch)
        return self.context

    async def stop(self) -> None:
        if self.context is not None:
            with contextlib.suppress(Exception):
                await self.context.close()
            self.context = None
        if self._playwright is not None:
            with contextlib.suppress(Exception):
                await self._playwright.stop()
            self._playwright = None
        if self.bridge is not None:
            await self.bridge.stop()
            self.bridge = None

    # --- helpers ----------------------------------------------------------

    @staticmethod
    def _needs_own_position(plan: fpmap.Plan) -> bool:
        return "geolocation" in plan.follow and plan.geo_permission != "block"

    async def _apply_geolocation(self) -> None:
        plan = self._plan
        geo = self.geo
        has_fix = bool(geo and geo.latitude is not None and geo.longitude is not None)
        if plan is None:
            # Only the position is emulated; sites still have to ask for permission.
            if has_fix:
                await self.context.set_geolocation(
                    {"latitude": geo.latitude, "longitude": geo.longitude, "accuracy": 50}
                )
            return
        position = plan.position
        if position is None and "geolocation" in plan.follow and has_fix:
            position = {"latitude": geo.latitude, "longitude": geo.longitude, "accuracy": 50}
        if position is not None and plan.geo_permission != "block":
            await self.context.set_geolocation(position)
        masked = plan.position is not None or "geolocation" in plan.follow
        if plan.geo_permission == "allow":
            if masked and position is None:
                # Granting now would hand sites this machine's real position.
                self.warnings.append("Geolocation is not allowed: there is no position to give")
            else:
                await self.context.grant_permissions(["geolocation"])

    def _resolve_executable(self) -> Path:
        if self._executable:
            path = Path(self._executable)
            if not path.is_file():
                raise EngineNotInstalled(f"Browser executable not found: {path}")
            return path
        installed = fetch.installed_executable(self._version)
        if not installed:
            raise EngineNotInstalled(
                "fingerprint-chromium is not installed; run: python -m chrome_engine fetch"
            )
        return installed

    def _resolve_persona(self) -> personas.Persona:
        plan = self._plan
        if self._persona is not None:
            pinned = {
                k: v or None
                for k, v in (("timezone", self._timezone), ("locale", self._locale))
                if v is not None
            }
            persona = replace(self._persona, **pinned)
        elif plan is not None:
            persona = personas.load_or_create(self.profile_dir, self._platform or host_os())
        else:
            persona = personas.load_or_create(
                self.profile_dir,
                self._platform or host_os(),
                timezone=self._timezone,
                locale=self._locale,
            )
        if plan is not None:
            # In memory only: the settings can change at any launch, and mask / real
            # must get the seed's cores and the exit IP's timezone back.
            persona = replace(
                persona,
                hardware_concurrency=plan.cores or persona.hardware_concurrency,
                timezone=plan.timezone,
                locale=plan.locale,
            )
            personas.validate(persona)
        level, reason = personas.compatibility(host_os(), persona.platform)
        if level == personas.UNSUPPORTED and not self._allow_unsupported:
            raise EngineError(
                f"A {persona.platform} persona cannot be presented consistently on a "
                f"{host_os()} host: {reason}"
            )
        if level != personas.OK:
            self.warnings.append(f"{persona.platform} persona on {host_os()}: {reason}")
        return persona

    async def _lookup_geo(self) -> ExitGeo:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None, lookup, self.bridge.url if self.bridge else None
            )
        except Exception as e:
            # Launching anyway would show the host's timezone behind the proxy.
            raise EngineError(
                f"Could not place the proxy's exit IP ({type(e).__name__}: {e}); "
                "pin a timezone and locale or pass geoip=False"
            ) from e

    def _ignored_default_args(self) -> list[str]:
        ignored = list(IGNORED_DEFAULT_ARGS)
        features = playwright_disabled_features_arg()
        if features:
            ignored.append(features)
        else:
            self.warnings.append(
                "Playwright's --disable-features list could not be removed: third-party "
                "storage partitioning and HTTPS upgrades stay off"
            )
        return ignored

    def _watch(self, page: Any) -> None:
        page.on("crash", lambda p: self.crashes.append(p.url))
