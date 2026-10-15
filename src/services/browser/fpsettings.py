"""Per-profile fingerprint settings for the Camoufox engine.

A profile's settings are {item: {"mode": str, "value": any}} for the items in
ITEMS. The frozen "masked" device (fingerprint.py) is the base; `apply_modes`
changes it per item: mask keeps the device value (or follows the exit IP for
timezone / language / geolocation / WebRTC), custom overwrites it, real removes
the key so the browser reports the host's own value, off / noise are
item-specific. `build_launch` is the one launch recipe shared by runner.py and
cookie_tool.py.
"""

import ipaddress
import json
import pathlib
import re
import warnings
from collections.abc import Callable
from typing import Any, NamedTuple

from ...core.config import HOST_OS, PROFILES_FILE
from ...utils.validation import valid_or_none, validate_locale, validate_timezone
from . import devices, fingerprint

OSES = ("windows", "macos", "linux")
_KEY = {"windows": "win", "macos": "mac", "linux": "lin"}
_PLATFORM = {"windows": "Win32", "macos": "MacIntel", "linux": "Linux"}
_OSCPU = {
    "Win32": "Windows NT 10.0; Win64; x64",
    "MacIntel": "Intel Mac OS X 10.15",
    "Linux x86_64": "Linux x86_64",
}
_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


# --- Item table ---------------------------------------------------------------


class Item(NamedTuple):
    modes: tuple[str, ...]
    default: str
    check: Callable[[Any, str], Any] | None = None  # validates the value of "custom"
    value: Any = None  # the default mode's value


def _fail(message: str) -> None:
    raise ValueError(message)


def _text(low: int, high: int) -> Callable[[Any, str], str]:
    def check(v: Any, _os: str) -> str:
        if not isinstance(v, str) or not low <= len(v.strip()) <= high:
            _fail(f"must be a text of {low}-{high} characters")
        return v.strip()

    return check


def _number(low: float, high: float, integer: bool = True) -> Callable[[Any, str], Any]:
    def check(v: Any, _os: str) -> Any:
        ok = isinstance(v, int) if integer else isinstance(v, (int, float))
        if isinstance(v, bool) or not ok or not low <= v <= high:
            _fail(f"must be a {'whole ' if integer else ''}number between {low} and {high}")
        return v

    return check


def _os_value(v: Any, os: str) -> str:
    if v is not None and v not in OSES:
        _fail(f"must be one of: {', '.join(OSES)}")
    return os  # the custom OS is always the profile's own OS


def _gpu(v: Any, _os: str) -> dict:
    if not isinstance(v, dict) or not all(isinstance(v.get(k), str) and v[k] for k in _VR):
        _fail('must be {"vendor": str, "renderer": str}')
    return {k: v[k] for k in _VR}


_VR = ("vendor", "renderer")


def _ip(v: Any, _os: str) -> str:
    try:
        return str(ipaddress.ip_address(v))
    except ValueError:
        raise ValueError("must be an IPv4 or IPv6 address") from None


def _timezone(v: Any, _os: str) -> str:
    ok, msg = (
        validate_timezone(v) if isinstance(v, str) and v else (False, "must be an IANA timezone")
    )
    if not ok:
        _fail(msg)
    return v


def _language(v: Any, _os: str) -> str:
    parts = [p.strip() for p in v.split(",")] if isinstance(v, str) else []
    for part in parts:
        ok, msg = validate_locale(part) if part else (False, "must be a language-REGION locale")
        if not ok:
            _fail(msg)
    return ",".join(parts)


def _field(name: str, check: Callable[[Any, str], Any], value: Any) -> Any:
    try:
        return check(value, "")
    except ValueError as e:
        raise ValueError(f"{name} {e}") from None


def _geolocation(v: Any, _os: str) -> dict:
    if not isinstance(v, dict):
        _fail('must be {"latitude": n, "longitude": n, "accuracy": n}')
    return {
        "latitude": _field("latitude", _number(-90, 90, integer=False), v.get("latitude")),
        "longitude": _field("longitude", _number(-180, 180, integer=False), v.get("longitude")),
        "accuracy": _field("accuracy", _number(1, 100_000, integer=False), v.get("accuracy", 50)),
    }


def _screen(v: Any, _os: str) -> str:
    m = re.fullmatch(r"(\d{3,5})x(\d{3,5})", v) if isinstance(v, str) else None
    if not m or not all(320 <= int(g) <= 16384 for g in m.groups()):
        _fail('must be "WIDTHxHEIGHT", e.g. "1920x1080"')
    return v


def _fonts(v: Any, _os: str) -> list[str]:
    if not isinstance(v, list) or not 1 <= len(v) <= 2000:
        _fail("must be a list of 1-2000 font names")
    names = [_text(1, 100)(n, _os) for n in v]
    return list(dict.fromkeys(names))


def _media(v: Any, _os: str) -> dict:
    if not isinstance(v, dict):
        _fail('must be {"micros": n, "webcams": n, "speakers": n}')
    return {k: _field(k, _number(0, 10), v.get(k)) for k in _MEDIA_KINDS}


_MEDIA_KINDS = ("micros", "webcams", "speakers")


def _hosts(v: Any, _os: str) -> list[str]:
    if not isinstance(v, list) or len(v) > 100:
        _fail("must be a list of up to 100 hostnames / IP addresses (no ports)")
    for host in v:
        if not isinstance(host, str) or not (_HOST.match(host) or _is_ip(host)):
            _fail(f"{host!r} is not a hostname or IP address (ports are not supported)")
    return list(dict.fromkeys(v))


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


_MCR = ("mask", "custom", "real")
ITEMS: dict[str, Item] = {
    "os": Item(_MCR, "custom", _os_value),
    "user_agent": Item(_MCR, "mask", _text(10, 400)),
    "platform": Item(_MCR, "mask", _text(1, 40)),
    "hardware_concurrency": Item(_MCR, "mask", _number(1, 128)),
    "webgl_meta": Item((*_MCR, "off"), "mask", _gpu),
    "webgl_noise": Item(("noise", "real"), "noise"),
    "canvas": Item(("noise", "real"), "noise"),
    "audio": Item(("noise", "real"), "noise"),
    "webrtc": Item((*_MCR, "off"), "mask", _ip),
    "timezone": Item(_MCR, "mask", _timezone),
    "geo_permission": Item(("prompt", "allow", "block"), "allow"),
    "geolocation": Item(_MCR, "mask", _geolocation),
    "language": Item(_MCR, "custom", _language, "en-US"),
    "screen": Item(_MCR, "mask", _screen),
    "fonts": Item(_MCR, "mask", _fonts),
    "media_devices": Item((*_MCR, "off"), "mask", _media),
    "voices": Item(("mask", "real", "off"), "mask"),
    "port_scan": Item(_MCR, "mask", _hosts),
}


# --- Normalizing ----------------------------------------------------------------


def defaults(os: str) -> dict[str, dict]:
    return {
        name: {"mode": it.default, "value": os if name == "os" else it.value}
        for name, it in ITEMS.items()
    }


def normalize(raw: Any, os: str) -> dict[str, dict]:
    """Complete, validated settings; missing items get their defaults.

    Raises ValueError naming the item for an unknown item, mode or bad value.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("fingerprint settings must be an object")
    if unknown := sorted(set(raw) - set(ITEMS)):
        raise ValueError(f"unknown fingerprint item(s): {', '.join(unknown)}")
    out = defaults(os)
    for name, entry in raw.items():
        item = ITEMS[name]
        if not isinstance(entry, dict) or entry.get("mode") not in item.modes:
            raise ValueError(f"{name}: mode must be one of: {', '.join(item.modes)}")
        mode, value = entry["mode"], None
        if mode == "custom":
            if entry.get("value") is None and name != "os":
                raise ValueError(f"{name}: custom mode needs a value")
            try:
                assert item.check is not None  # every item with a custom mode has a check
                value = item.check(entry.get("value"), os)
            except ValueError as e:
                raise ValueError(f"{name}: {e}") from e
        out[name] = {"mode": mode, "value": value}
    return out


def tolerant(raw: Any, os: str) -> dict[str, dict]:
    """normalize(), but an invalid item falls back to its default instead of failing."""
    if not isinstance(raw, dict):
        return defaults(os)
    good = {}
    for name, entry in raw.items():
        try:
            normalize({name: entry}, os)
        except ValueError:
            continue
        good[name] = entry
    return normalize(good, os)


def from_stored(raw: Any, os: str, timezone: str | None, locale: str | None) -> dict[str, dict]:
    """Settings of a stored profile, with its timezone / locale fields mirrored in.

    A profile saved before settings existed (no `fingerprint`) followed the exit IP
    unless it pinned a locale, so its language is "mask", not the new en-US default.
    """
    settings = tolerant(raw, os)
    if not isinstance(raw, dict) and not locale:
        settings["language"] = {"mode": "mask", "value": None}
    if timezone:
        settings["timezone"] = {"mode": "custom", "value": timezone}
    if locale:
        settings["language"] = {"mode": "custom", "value": locale}
    return settings


def geo_fields(settings: dict, partial: dict) -> dict[str, str | None]:
    """Profile.timezone / Profile.locale values implied by the items in `partial`."""
    out: dict[str, str | None] = {}
    for field, name in (("timezone", "timezone"), ("locale", "language")):
        if name in partial:
            item = settings[name]
            out[field] = item["value"] if item["mode"] == "custom" else None
    return out


def saved(profile_name: str, os: str, timezone: str = "", locale: str = "") -> dict[str, dict]:
    """The settings of a profile as stored in profiles.json (for the subprocesses)."""
    try:
        data = json.loads(pathlib.Path(PROFILES_FILE).read_text(encoding="utf-8"))[profile_name]
        raw = data.get("fingerprint")
    except (OSError, ValueError, KeyError, AttributeError):
        raw = None
    return from_stored(
        raw, os, valid_or_none(timezone, validate_timezone), valid_or_none(locale, validate_locale)
    )


def launch_os(settings: dict, os_type: str) -> str:
    return HOST_OS if settings["os"]["mode"] == "real" else os_type


def needs_ip(settings: dict) -> bool:
    """Whether any item follows the exit IP (so a lookup is worth making)."""
    return any(
        settings[n]["mode"] == "mask" for n in ("webrtc", "timezone", "geolocation", "language")
    )


# --- Applying the modes ---------------------------------------------------------

_FIREFOX = (re.compile(r"Firefox/\d+\.0"), re.compile(r"rv:\d+\.0"))


def rewrite_version(config: dict, major: str) -> None:
    """Point the Firefox version in the UA at the installed build (as from_preset does)."""
    for key in ("navigator.userAgent", "headers.User-Agent"):
        if isinstance(config.get(key), str):
            config[key] = _FIREFOX[0].sub(f"Firefox/{major}.0", config[key])
            config[key] = _FIREFOX[1].sub(f"rv:{major}.0", config[key])


def _pop(config: dict, *prefixes: str) -> None:
    for key in [k for k in config if k.startswith(prefixes)]:
        del config[key]


def _resize_screen(config: dict, size: str) -> None:
    from camoufox.fingerprints import clamp_window_dimensions, clamp_window_position

    w, h = (int(n) for n in size.split("x"))
    for axis, new in (("Width", w), ("Height", h)):
        old = config.get(f"screen.{axis.lower()}", new)
        taskbar = max(0, old - config.get(f"screen.avail{axis}", old))  # keep the taskbar delta
        config[f"screen.{axis.lower()}"] = new
        config[f"screen.avail{axis}"] = max(1, new - taskbar)
    clamp_window_dimensions(config)
    clamp_window_position(config)


def _media_devices(config: dict, counts: dict) -> None:
    for kind, count_key, singular in (
        ("micros", "microphone", "Microphone"),
        ("webcams", "webcam", "Webcam"),
        ("speakers", "speaker", "Speaker"),
    ):
        n = counts[kind]
        labels = list(config.get(f"mediaDevices:{count_key}Labels", []))[:n]
        groups = list(config.get(f"mediaDevices:{count_key}Groups", []))[:n]
        labels += [f"{singular} {i + 1}" for i in range(len(labels), n)]
        groups += [f"hw-{100 + i}" for i in range(len(groups), n)]
        config[f"mediaDevices:{kind}"] = n
        config[f"mediaDevices:{count_key}Labels"] = labels
        config[f"mediaDevices:{count_key}Groups"] = groups
    config["mediaDevices:enabled"] = True


def apply_modes(
    config: dict,
    prefs: dict,
    settings: dict,
    os: str,
    *,
    geo: dict | None = None,
    ip: str | None = None,
    proxy: bool = False,
    ff_major: str | None = None,
) -> list[str]:
    """Change the frozen device `config` and Firefox `prefs` in place per `settings`.

    `geo` is camoufox's Geolocation.as_config() for the exit IP and `ip` the exit IP;
    without them the follow-the-IP items are left alone. Returns notes worth logging.
    Every pref is assigned in both states: a persistent profile keeps old prefs.
    """
    notes: list[str] = []
    mode = {name: s["mode"] for name, s in settings.items()}
    value = {name: s["value"] for name, s in settings.items()}
    key = _KEY[os]

    # navigator
    if mode["user_agent"] == "custom":
        config["navigator.userAgent"] = value["user_agent"]
        if "headers.User-Agent" in config:
            config["headers.User-Agent"] = value["user_agent"]
        from camoufox.fingerprints import _app_version_from_user_agent

        if app_version := _app_version_from_user_agent(value["user_agent"]):
            config["navigator.appVersion"] = app_version
    elif mode["user_agent"] == "real":
        _pop(config, "navigator.userAgent", "navigator.appVersion", "headers.User-Agent")
    elif ff_major:
        rewrite_version(config, ff_major)
    if mode["platform"] == "custom":
        config["navigator.platform"] = value["platform"]
        if value["platform"] in _OSCPU:
            config["navigator.oscpu"] = _OSCPU[value["platform"]]
    elif mode["platform"] == "real":
        _pop(config, "navigator.platform", "navigator.oscpu")
    if mode["hardware_concurrency"] == "custom":
        config["navigator.hardwareConcurrency"] = value["hardware_concurrency"]
    elif mode["hardware_concurrency"] == "real":
        _pop(config, "navigator.hardwareConcurrency")

    # WebGL (before the audio seed: the seed also keys the GPU's recorded draw)
    prefs["webgl.disabled"] = mode["webgl_meta"] == "off"
    if mode["webgl_meta"] == "real":
        _pop(config, "webGl:", "webGl2:")
    elif mode["webgl_meta"] == "custom":
        from camoufox.webgl import webgl_for_gpu

        gpu = value["webgl_meta"]
        try:
            block = webgl_for_gpu(
                key, gpu["vendor"], gpu["renderer"], seed=config.get("audio:seed")
            )
        except ValueError:
            notes.append(
                f"WebGL GPU {gpu['renderer']!r} has no recorded data for {os}; using the device's GPU"
            )
        else:
            _pop(config, "webGl:", "webGl2:")
            prefs["webgl.enable-webgl2"] = block.pop("webGl2Enabled")
            config.update(block)

    # Noise: canvas and WebGL readback share Firefox's fingerprinting protection
    targets = [
        target
        for item, target in (
            ("canvas", "+CanvasRandomization"),
            ("webgl_noise", "+WebGLRandomization"),
        )
        if mode[item] == "noise"
    ]
    prefs["privacy.fingerprintingProtection"] = bool(targets)
    prefs["privacy.fingerprintingProtection.overrides"] = (
        ",".join(["-AllTargets", *targets]) if targets else ""
    )
    if mode["audio"] == "real":
        config["audio:seed"] = 0

    # WebRTC
    _pop(config, "webrtc:")
    spoof_ip = (
        value["webrtc"] if mode["webrtc"] == "custom" else ip if mode["webrtc"] == "mask" else None
    )
    v4 = False
    if spoof_ip:
        v4 = isinstance(ipaddress.ip_address(spoof_ip), ipaddress.IPv4Address)
        config["webrtc:ipv4" if v4 else "webrtc:ipv6"] = spoof_ip
    prefs["media.peerconnection.enabled"] = mode["webrtc"] != "off"
    prefs["network.dns.disableIPv6"] = v4

    # Timezone, language, geolocation
    config.pop("timezone", None)
    if mode["timezone"] == "custom":
        config["timezone"] = value["timezone"]
    elif mode["timezone"] == "mask" and geo:
        config["timezone"] = geo["timezone"]
    _pop(config, "locale:")
    if mode["language"] == "custom":
        from camoufox.locales import handle_locales

        handle_locales(value["language"], config)
    elif mode["language"] == "mask" and geo:
        config.update({k: v for k, v in geo.items() if k.startswith("locale:")})
    if config.get("locale:language"):
        parts = (
            config["locale:language"],
            config.get("locale:script"),
            config.get("locale:region"),
        )
        prefs["intl.locale.requested"] = "-".join(p for p in parts if p)
    else:
        prefs["intl.locale.requested"] = "" if mode["language"] == "real" else "en-US"
    _pop(config, "geolocation:")
    if mode["geolocation"] == "custom":
        config.update({f"geolocation:{k}": v for k, v in value["geolocation"].items()})
    elif mode["geolocation"] == "mask" and geo:
        config.update({k: v for k, v in geo.items() if k.startswith("geolocation:")})
    prefs["permissions.default.geo"] = {"prompt": 0, "allow": 1, "block": 2}[mode["geo_permission"]]
    if mode["geo_permission"] == "block":
        _pop(config, "geolocation:")  # spoofed coordinates would bypass the denial

    # Screen
    if mode["screen"] == "real":
        _pop(config, "screen.", "window.")
    elif mode["screen"] == "custom":
        _resize_screen(config, value["screen"])

    # Fonts, media devices, voices
    if mode["fonts"] == "custom":
        config["fonts"] = value["fonts"]
    elif mode["fonts"] == "real":
        config.pop("fonts", None)
    if mode["media_devices"] == "real":
        config["mediaDevices:enabled"] = False  # spoofing off: the host's devices show
    elif mode["media_devices"] == "off":
        _media_devices(config, dict.fromkeys(_MEDIA_KINDS, 0))
    elif mode["media_devices"] == "custom":
        _media_devices(config, value["media_devices"])
    if mode["voices"] == "off":
        config["voices"] = []
        config["voices:blockIfNotDefined"] = True
    elif mode["voices"] == "real":
        config.pop("voices", None)
        config["voices:blockIfNotDefined"] = False
    else:
        config["voices:blockIfNotDefined"] = True

    # Local network access (port scanning from pages)
    scan = mode["port_scan"] != "real"
    prefs["network.lna.enabled"] = scan
    prefs["network.lna.blocking"] = scan
    prefs["network.lna.websocket.enabled"] = scan
    prefs["network.lna.skip-domains"] = (
        ",".join(value["port_scan"]) if mode["port_scan"] == "custom" else ""
    )
    prefs["network.proxy.allow_hijacking_localhost"] = proxy and scan
    return notes


# --- Launch ----------------------------------------------------------------------


def build_launch(
    profile_dir: str,
    settings: dict,
    os_type: str,
    *,
    proxy: dict | None = None,
    headless: bool = True,
    ip: str | None = None,
    virtual_display: str | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Launch options for AsyncCamoufox(from_options=..., persistent_context=True).

    Blocking (it may download the GeoIP database); call it off the event loop.
    `ip` is the exit IP, None where there is no network use (cookie_tool).
    """
    from camoufox import coherence
    from camoufox._warnings import LeakWarning
    from camoufox.geolocation import get_geolocation
    from camoufox.utils import (
        get_env_vars,
        get_pref_env_vars,
        launch_options,
        resolve_verstr,
        validate_config,
    )

    os = launch_os(settings, os_type)
    device = fingerprint.load_or_create(profile_dir, os)
    with warnings.catch_warnings():
        # "proxy without geoip": the geo is applied below instead.
        warnings.simplefilter("ignore", LeakWarning)
        opts = launch_options(
            headless=headless,
            os=os,
            config=dict(device),
            proxy=proxy,
            user_data_dir=profile_dir,
            humanize=True,
            block_images=False,
            i_know_what_im_doing=True,
            virtual_display=virtual_display,
        )
    env, prefs = opts["env"], opts["firefox_user_prefs"]
    config = fingerprint.decode_config(env)
    exe = pathlib.Path(opts["executable_path"])
    geo = get_geolocation(ip).as_config() if ip and needs_ip(settings) else None
    for note in apply_modes(
        config,
        prefs,
        settings,
        os,
        geo=geo,
        ip=ip,
        proxy=bool(proxy),
        ff_major=resolve_verstr(exe).split(".")[0],
    ):
        log(note)
    validate_config(config, path=exe)
    for violation in coherence.validate(config, _KEY[os]):
        log(f"Fingerprint coherence ({violation.rule}): {violation.detail}")
    for name in [n for n in env if n.startswith(("CAMOU_CONFIG_", "CAMOU_PREFS_"))]:
        del env[name]
    env.update(get_env_vars(config, _KEY[os], path=exe))
    env.update(get_pref_env_vars(prefs))
    return opts


# --- Coherence warnings and UI options -----------------------------------------


def check(
    settings: dict,
    device: dict | None,
    os: str,
    host_os: str,
    proxy: bool = False,
) -> list[str]:
    """Human-readable warnings about combinations a site could notice."""
    mode = {name: s["mode"] for name, s in settings.items()}
    value = {name: s["value"] for name, s in settings.items()}
    out: list[str] = []
    if mode["user_agent"] == "custom":
        from camoufox.utils import determine_ua_os

        try:
            if determine_ua_os(value["user_agent"]) != _KEY[os]:
                out.append(f"The custom user agent names a different OS than the profile's {os}.")
        except ValueError:
            out.append("The custom user agent does not name an OS.")
    if mode["platform"] == "custom" and not value["platform"].startswith(_PLATFORM[os]):
        out.append(f"The custom platform {value['platform']!r} does not match the profile's {os}.")
    if mode["webgl_meta"] == "custom":
        gpus = devices.gpus(os)
        if value["webgl_meta"] not in gpus:
            out.append(f"The custom GPU is not a known {os} GPU; pick one from the options list.")
    if os != host_os:
        out += [
            f"{name} is real but the profile's OS ({os}) differs from this machine's ({host_os})."
            for name in ("user_agent", "platform", "fonts", "webgl_meta", "screen")
            if mode[name] == "real"
        ]
    if mode["hardware_concurrency"] == "custom" and host_os == "macos":
        out.append(
            "macOS cannot pin CPU cores: a custom core count is not backed by real parallelism."
        )
    if mode["geo_permission"] == "prompt" and mode["geolocation"] != "real":
        out.append(
            "Geolocation 'prompt' still delivers the position without asking, which sites can notice."
        )
    if mode["media_devices"] == "real":
        out.append("Real media devices expose this machine's microphones, cameras and speakers.")
    if proxy:
        out += [
            f"{name} is real while a proxy is set: it will not match the proxy's location."
            for name in ("webrtc", "timezone", "language")
            if mode[name] == "real"
        ]
    return out


def options(os: str) -> dict:
    """Choices for the settings UI: GPUs, screens and fonts of `os`, and the item table."""
    from camoufox.fingerprints import _load_os_fonts

    return {
        "gpus": devices.gpus(os),
        "screens": devices.screens(os),
        "fonts": list(_load_os_fonts().get(_KEY[os], [])),
        "items": {
            name: {
                "modes": list(it.modes),
                "default": {"mode": it.default, "value": defaults(os)[name]["value"]},
            }
            for name, it in ITEMS.items()
        },
    }
