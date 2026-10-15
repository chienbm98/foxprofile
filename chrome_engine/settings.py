"""Map a profile's fingerprint settings onto the Chrome engine.

`settings` is {item: {"mode", "value"}} as stored by src/services/browser/fpsettings.py
(CHROME_ITEMS lists what the engine honours); this module stays free of src imports.
Every mapping was checked against the pinned fingerprint-chromium build:

- canvas / audio "real": --disable-spoofing=canvas|audio (canvas also covers WebGL
  read-back noise); webgl_meta "real": --disable-spoofing=gpu (the host's renderer);
- hardware_concurrency: the persona's, a custom number, or this machine's;
- timezone / language: the exit IP's (mask), a custom value, or the host's (real);
- webrtc: mask = no LAN address, off = no UDP at all, real = the browser default;
- port_scan: mask = Local Network Access denied for pages, real = checks disabled;
- geolocation / geo_permission: Playwright's emulated position and permission grant
  plus the profile's default geolocation content setting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WEBRTC_PROXY = "disable_non_proxied_udp"
WEBRTC_DIRECT = "default_public_interface_only"
_LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
_CONTENT = "profile.default_content_setting_values."
# Chromium content-setting values.
_BLOCK, _ASK = 2, 3


@dataclass(frozen=True)
class Plan:
    """What a settings object asks of one launch."""

    cores: int | None  # None: the persona's own
    timezone: str | None  # a custom value; None: unset
    locale: str | None
    follow: frozenset[str]  # of timezone / locale / geolocation: take from the exit IP
    position: dict | None  # a custom geolocation
    geo_permission: str
    webrtc: str
    spoofing_off: tuple[str, ...]
    port_scan_real: bool

    def args(self) -> list[str]:
        out: list[str] = []
        if self.spoofing_off:
            out.append(f"--disable-spoofing={','.join(self.spoofing_off)}")
        if self.webrtc == "real":
            # fingerprint-chromium hides every candidate unless this switch says otherwise
            out.append("--webrtc-ip-handling-policy=default")
        if self.port_scan_real:
            out.append("--disable-features=LocalNetworkAccessChecks")
        return out

    def prefs(self, proxied: bool) -> dict[str, object]:
        """Profile preferences, written on every launch (a profile keeps stale ones)."""
        policy = {
            "mask": WEBRTC_PROXY if proxied else WEBRTC_DIRECT,
            "off": WEBRTC_PROXY,
            "real": "default",
        }[self.webrtc]
        scan = None if self.port_scan_real else _BLOCK  # None: the key is removed
        return {
            "webrtc.ip_handling_policy": policy,
            _CONTENT + "geolocation": _BLOCK if self.geo_permission == "block" else _ASK,
            _CONTENT + "local_network_access": scan,
            _CONTENT + "loopback_network": scan,
        }


def first_locale(value: str | None) -> str | None:
    """The first language of a custom list ("en-US,vi-VN"), if the engine can use it."""
    first = (value or "").split(",")[0].strip()
    return first if _LOCALE.match(first) else None


def plan(settings: dict, host_cpus: int) -> Plan:
    mode = {name: s["mode"] for name, s in settings.items()}
    value = {name: s["value"] for name, s in settings.items()}
    cores = {
        "mask": None,
        "custom": value["hardware_concurrency"],
        "real": max(1, min(64, host_cpus)),
    }[mode["hardware_concurrency"]]
    follow = {
        field
        for field, item in (
            ("timezone", "timezone"),
            ("locale", "language"),
            ("geolocation", "geolocation"),
        )
        if mode[item] == "mask"
    }
    return Plan(
        cores=cores,
        timezone=value["timezone"] if mode["timezone"] == "custom" else None,
        locale=first_locale(value["language"]) if mode["language"] == "custom" else None,
        follow=frozenset(follow),
        position=value["geolocation"] if mode["geolocation"] == "custom" else None,
        geo_permission=mode["geo_permission"],
        webrtc=mode["webrtc"],
        spoofing_off=tuple(
            flag
            for item, flag in (("canvas", "canvas"), ("audio", "audio"), ("webgl_meta", "gpu"))
            if mode[item] == "real"
        ),
        port_scan_real=mode["port_scan"] == "real",
    )
