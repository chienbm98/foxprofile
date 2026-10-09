"""probe.check against hand-built fingerprints."""

import copy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from chrome_engine import probe
from chrome_engine.persona import Persona

PERSONA = Persona(
    seed=9,
    platform="windows",
    platform_version="19.0.0",
    brand="Chrome",
    hardware_concurrency=8,
    timezone="Asia/Ho_Chi_Minh",
    locale="vi-VN",
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


def _offset(name):
    return -int(
        datetime.now(timezone.utc).astimezone(ZoneInfo(name)).utcoffset().total_seconds() // 60
    )


def good_fp():
    identity = {
        "userAgent": UA,
        "platform": "Win32",
        "languages": ["vi-VN", "vi", "en-US", "en"],
        "hardwareConcurrency": 8,
        "deviceMemory": 8,
        "timezone": "Asia/Saigon",
        "webdriver": False,
    }
    return {
        "main": dict(identity),
        "worker": dict(identity),
        "iframe": dict(identity),
        "serviceWorker": {**identity, "webdriver": None},
        "sharedWorker": {**identity, "webdriver": None},
        "uaData": {
            "platform": "Windows",
            "platformVersion": "19.0.0",
            "brands": [{"brand": "Chromium"}, {"brand": "Google Chrome"}, {"brand": "Not/A)Brand"}],
        },
        "headers": {
            "user-agent": UA,
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148"',
            "accept-language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        "webgl": {
            "vendor": "Google Inc. (Intel)",
            "renderer": "ANGLE (Intel, Iris Xe Direct3D11 vs_5_0 ps_5_0, D3D11)",
        },
        "cdpDetected": False,
        "webrtcCandidates": [],
        "screen": {"width": 1920, "height": 1080},
        "window": {"innerWidth": 1900},
        "scrollbarWidth": 15,
        "timezoneOffset": _offset("Asia/Ho_Chi_Minh"),
    }


def codes(fp, persona=PERSONA):
    return {i.code for i in probe.check(persona, fp)}


def test_coherent_fingerprint_has_no_issues():
    assert probe.check(PERSONA, good_fp()) == []


def _set(fp, path, value):
    target = fp
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (("main", "userAgent"), UA.replace("Windows NT 10.0", "X11; Linux x86_64"), "ua_os"),
        (("main", "platform"), "MacIntel", "navigator_platform"),
        (("main", "hardwareConcurrency"), 32, "hardware_concurrency"),
        (("main", "webdriver"), True, "webdriver"),
        (("main", "timezone"), "Europe/Berlin", "timezone"),
        (("timezoneOffset",), 0, "timezone_offset"),
        (("main", "languages"), ["en-US"], "language"),
        (("worker", "platform"), "Linux x86_64", "worker_platform"),
        (("worker", "hardwareConcurrency"), 4, "worker_hardwareConcurrency"),
        (("iframe", "userAgent"), "HeadlessChrome", "iframe_userAgent"),
        (("worker",), {"error": "timeout"}, "worker_error"),
        (("serviceWorker", "hardwareConcurrency"), 12, "serviceWorker_hardwareConcurrency"),
        (("serviceWorker", "timezone"), "UTC", "serviceWorker_timezone"),
        (("sharedWorker", "languages"), ["en-US"], "sharedWorker_languages"),
        (("sharedWorker",), {"error": "SecurityError"}, "sharedWorker_error"),
        (("uaData", "platform"), "Linux", "uadata_platform"),
        (("uaData", "platformVersion"), "10.0.0", "uadata_platform_version"),
        (("uaData", "brands"), [{"brand": "Chromium"}], "brand"),
        (("headers", "user-agent"), "curl/8", "header_user_agent"),
        (("headers", "sec-ch-ua-platform"), '"Linux"', "header_platform"),
        (("headers", "sec-ch-ua"), '"Chromium";v="148"', "header_brand"),
        (("headers", "accept-language"), "en-US", "header_language"),
        (("webgl", "renderer"), "ANGLE (Apple, ANGLE Metal Renderer: Apple M2)", "webgl_renderer"),
        (("webgl",), {"error": "no context"}, "webgl_unavailable"),
        (("cdpDetected",), True, "cdp_runtime"),
        (
            ("webrtcCandidates",),
            ["candidate:1 1 udp 2122260223 192.168.1.20 54321 typ host"],
            "webrtc_ip",
        ),
        (("screen",), {"width": 800, "height": 600}, "screen_default"),
        (("window", "innerWidth"), 2560, "screen_window"),
        (("scrollbarWidth",), 0, "scrollbar_width"),
    ],
)
def test_each_mismatch_is_reported(path, value, code):
    fp = copy.deepcopy(good_fp())
    _set(fp, path, value)
    assert code in codes(fp)


def test_headless_user_agent():
    fp = good_fp()
    fp["main"]["userAgent"] = fp["main"]["userAgent"].replace("Chrome/", "HeadlessChrome/")
    assert "ua_headless" in codes(fp)


def test_mdns_candidates_are_not_leaks():
    fp = good_fp()
    fp["webrtcCandidates"] = ["candidate:1 1 udp 2122260223 3f9a.local 54321 typ host"]
    assert "webrtc_ip" not in codes(fp)


def test_macos_scrollbars_may_be_overlay():
    persona = Persona(seed=1, platform="macos", platform_version="15.6.1")
    fp = good_fp()
    fp["scrollbarWidth"] = 0
    assert "scrollbar_width" not in codes(fp, persona)


def test_unpinned_persona_skips_geo_checks():
    persona = Persona(seed=9, platform="windows", platform_version="19.0.0", hardware_concurrency=8)
    fp = good_fp()
    fp["main"]["timezone"] = "America/New_York"
    fp["timezoneOffset"] = 300
    assert not {"timezone", "timezone_offset", "language", "header_language"} & codes(fp, persona)


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("Asia/Saigon", "Asia/Ho_Chi_Minh", True),
        ("Asia/Calcutta", "Asia/Kolkata", True),
        ("Europe/Kiev", "Europe/Kyiv", True),
        ("Europe/Paris", "Europe/Berlin", True),  # same rules all year
        ("Europe/London", "Europe/Paris", False),
        ("America/New_York", "America/Phoenix", False),
        ("Not/AZone", "UTC", False),
    ],
)
def test_same_timezone(a, b, same):
    assert probe.same_timezone(a, b) is same


@pytest.mark.parametrize(
    ("renderer", "platform", "ok"),
    [
        (
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "windows",
            True,
        ),
        ("ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)", "macos", True),
        ("ANGLE (Intel, Mesa Intel(R) UHD Graphics 620 (KBL GT2), OpenGL 4.6)", "linux", True),
        (
            "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "linux",
            False,
        ),
        ("ANGLE (Apple, ANGLE Metal Renderer: Apple M1)", "windows", False),
    ],
)
def test_webgl_platform_match(renderer, platform, ok):
    assert probe._webgl_matches(platform, renderer) is ok


def test_chrome_major():
    assert probe.chrome_major(good_fp()) == 148
    assert probe.chrome_major({}) is None
