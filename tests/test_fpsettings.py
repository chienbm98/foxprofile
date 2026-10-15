"""Fingerprint settings: validation, the per-mode changes to a frozen device, warnings, REST."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container
from src.services.browser import devices, fingerprint, fpsettings
from src.services.profile.manager import ProfileManager

DEVICE = {
    "navigator.userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
    "navigator.appVersion": "5.0 (Windows)",
    "navigator.platform": "Win32",
    "navigator.oscpu": "Windows NT 10.0; Win64; x64",
    "navigator.hardwareConcurrency": 8,
    "screen.width": 1920,
    "screen.height": 1080,
    "screen.availWidth": 1920,
    "screen.availHeight": 1040,
    "window.outerWidth": 1920,
    "window.outerHeight": 1040,
    "window.screenX": 0,
    "window.screenY": 0,
    "webGl:vendor": "Old",
    "webGl:renderer": "Old GPU",
    "webGl:parameters": {"1": 1},
    "webGl2:parameters": {"1": 1},
    "audio:seed": 12345,
    "fonts": ["Arial", "Calibri"],
    "voices": [{"name": "Zira"}],
    "voices:blockIfNotDefined": True,
    "mediaDevices:enabled": True,
    "mediaDevices:micros": 1,
    "mediaDevices:webcams": 1,
    "mediaDevices:speakers": 1,
    "mediaDevices:microphoneLabels": ["Mic"],
    "mediaDevices:microphoneGroups": ["hw-1"],
    "mediaDevices:webcamLabels": ["Cam"],
    "mediaDevices:webcamGroups": ["hw-2"],
    "mediaDevices:speakerLabels": ["Spk"],
    "mediaDevices:speakerGroups": ["hw-1"],
}
GEO = {
    "timezone": "Europe/Paris",
    "locale:language": "fr",
    "locale:region": "FR",
    "geolocation:latitude": 48.85,
    "geolocation:longitude": 2.35,
}


def run(partial=None, os="windows", **kw):
    """(config, prefs, notes) after applying `partial` settings to the fake device."""
    config, prefs = copy.deepcopy(DEVICE), {}
    notes = fpsettings.apply_modes(config, prefs, fpsettings.normalize(partial, os), os, **kw)
    return config, prefs, notes


def item(mode, value=None):
    return {"mode": mode, "value": value}


# --- normalize -------------------------------------------------------------------


def test_defaults():
    d = fpsettings.defaults("macos")
    assert set(d) == set(fpsettings.ITEMS) and len(d) == 18
    assert d["os"] == item("custom", "macos")
    assert d["language"] == item("custom", "en-US")
    assert {n for n, s in d.items() if s["mode"] == "noise"} == {"canvas", "webgl_noise", "audio"}
    assert d["geo_permission"] == item("allow")
    assert d["port_scan"] == item("mask")
    assert {s["mode"] for n, s in d.items() if n not in ("canvas", "webgl_noise", "audio")} == {
        "custom",
        "mask",
        "allow",
    }


def test_normalize_fills_and_keeps():
    out = fpsettings.normalize({"hardware_concurrency": item("custom", 12)}, "linux")
    assert out["hardware_concurrency"] == item("custom", 12)
    assert out["os"] == item("custom", "linux")
    assert fpsettings.normalize(None, "linux") == fpsettings.defaults("linux")
    assert fpsettings.normalize(out, "linux") == out


def test_normalize_drops_value_of_other_modes():
    out = fpsettings.normalize({"webrtc": item("off", "1.2.3.4")}, "linux")
    assert out["webrtc"] == item("off")


@pytest.mark.parametrize(
    ("name", "entry", "message"),
    [
        ("nope", item("mask"), "unknown fingerprint item"),
        ("canvas", item("mask"), "canvas: mode must be one of"),
        ("canvas", "noise", "canvas: mode must be one of"),
        ("hardware_concurrency", item("custom"), "needs a value"),
        ("hardware_concurrency", item("custom", 0), "between 1 and 128"),
        ("hardware_concurrency", item("custom", True), "between 1 and 128"),
        ("user_agent", item("custom", "x"), "user_agent: must be a text"),
        ("webgl_meta", item("custom", {"vendor": "x"}), "vendor"),
        ("webrtc", item("custom", "not-an-ip"), "IPv4 or IPv6"),
        ("timezone", item("custom", "Mars/Base"), "timezone"),
        ("language", item("custom", "xx"), "locale"),
        ("geolocation", item("custom", {"latitude": 91, "longitude": 0}), "latitude"),
        ("geolocation", item("custom", {"latitude": 1}), "longitude"),
        ("screen", item("custom", "1920*1080"), "WIDTHxHEIGHT"),
        ("fonts", item("custom", []), "font names"),
        ("media_devices", item("custom", {"micros": 1}), "webcams"),
        ("port_scan", item("custom", ["127.0.0.1:80"]), "ports are not supported"),
        ("os", item("custom", "beos"), "one of"),
    ],
)
def test_normalize_rejects(name, entry, message):
    with pytest.raises(ValueError, match=message):
        fpsettings.normalize({name: entry}, "windows")


def test_normalize_rejects_non_object():
    with pytest.raises(ValueError, match="object"):
        fpsettings.normalize([1], "windows")


def test_normalize_custom_values():
    out = fpsettings.normalize(
        {
            "geolocation": item("custom", {"latitude": 1, "longitude": 2}),
            "port_scan": item("custom", ["127.0.0.1", "localhost", "127.0.0.1"]),
            "fonts": item("custom", ["A", "A", " B "]),
            "language": item("custom", "de-DE, en-US"),
            "webrtc": item("custom", "2001:db8::1"),
        },
        "windows",
    )
    assert out["geolocation"]["value"] == {"latitude": 1, "longitude": 2, "accuracy": 50}
    assert out["port_scan"]["value"] == ["127.0.0.1", "localhost"]
    assert out["fonts"]["value"] == ["A", "B"]
    assert out["language"]["value"] == "de-DE,en-US"
    assert out["webrtc"]["value"] == "2001:db8::1"


def test_tolerant_drops_only_the_bad_items():
    raw = {"canvas": item("real"), "screen": item("custom", "bad"), "zzz": item("mask")}
    out = fpsettings.tolerant(raw, "windows")
    assert out["canvas"] == item("real")
    assert out["screen"] == item("mask")
    assert fpsettings.tolerant("junk", "windows") == fpsettings.defaults("windows")


def test_from_stored_legacy_follows_the_ip():
    legacy = fpsettings.from_stored(None, "windows", None, None)
    assert legacy["language"] == item("mask") and legacy["timezone"] == item("mask")
    pinned = fpsettings.from_stored(None, "windows", "Asia/Tokyo", "ja-JP")
    assert pinned["timezone"] == item("custom", "Asia/Tokyo")
    assert pinned["language"] == item("custom", "ja-JP")
    new = fpsettings.from_stored({}, "windows", None, None)
    assert new["language"] == item("custom", "en-US")


# --- apply_modes ---------------------------------------------------------------


def test_default_settings_on_the_device():
    config, prefs, _ = run()
    assert config["navigator.userAgent"] == DEVICE["navigator.userAgent"]
    assert config["audio:seed"] == 12345
    assert (config["locale:language"], config["locale:region"]) == ("en", "US")
    assert prefs["intl.locale.requested"].endswith("US")
    assert prefs["privacy.fingerprintingProtection"] is True
    assert (
        prefs["privacy.fingerprintingProtection.overrides"]
        == "-AllTargets,+CanvasRandomization,+WebGLRandomization"
    )
    assert prefs["permissions.default.geo"] == 1
    assert prefs["media.peerconnection.enabled"] is True
    assert prefs["webgl.disabled"] is False
    assert prefs["network.dns.disableIPv6"] is False
    assert prefs["network.lna.enabled"] is True and prefs["network.lna.skip-domains"] == ""
    assert prefs["network.proxy.allow_hijacking_localhost"] is False
    assert "timezone" not in config and not any(k.startswith("geolocation:") for k in config)


def test_user_agent_modes():
    config, _, _ = run(ff_major="157")
    assert (
        "Firefox/157.0" in config["navigator.userAgent"]
        and "rv:157.0" in config["navigator.userAgent"]
    )
    ua = "Mozilla/5.0 (X11; Linux x86_64; rv:100.0) Gecko/20100101 Firefox/100.0"
    config, _, _ = run({"user_agent": item("custom", ua)}, ff_major="157")
    assert config["navigator.userAgent"] == ua  # a custom UA is the user's literal choice
    assert config["navigator.appVersion"] == "5.0 (X11)"
    config, _, _ = run({"user_agent": item("real")})
    assert not any(k in config for k in ("navigator.userAgent", "navigator.appVersion"))


def test_platform_and_cores():
    config, _, _ = run({"platform": item("custom", "MacIntel")})
    assert config["navigator.platform"] == "MacIntel"
    assert config["navigator.oscpu"] == "Intel Mac OS X 10.15"
    config, _, _ = run({"platform": item("custom", "Odd")})
    assert (
        config["navigator.platform"] == "Odd"
        and config["navigator.oscpu"] == DEVICE["navigator.oscpu"]
    )
    config, _, _ = run({"platform": item("real"), "hardware_concurrency": item("real")})
    assert not any(k in config for k in ("navigator.platform", "navigator.oscpu"))
    assert "navigator.hardwareConcurrency" not in config
    config, _, _ = run({"hardware_concurrency": item("custom", 4)})
    assert config["navigator.hardwareConcurrency"] == 4


def test_webgl_meta_modes():
    _, prefs, _ = run({"webgl_meta": item("off")})
    assert prefs["webgl.disabled"] is True
    config, prefs, _ = run({"webgl_meta": item("real")})
    assert (
        not any(k.startswith(("webGl:", "webGl2:")) for k in config)
        and prefs["webgl.disabled"] is False
    )
    gpu = devices.gpus("windows")[0]
    config, prefs, notes = run({"webgl_meta": item("custom", gpu)})
    assert (config["webGl:vendor"], config["webGl:renderer"]) == (gpu["vendor"], gpu["renderer"])
    assert config["webGl:parameters"] != DEVICE["webGl:parameters"]  # the whole block is replaced
    assert isinstance(prefs["webgl.enable-webgl2"], bool) and not notes
    config, _, notes = run({"webgl_meta": item("custom", {"vendor": "X", "renderer": "Nope"})})
    assert config["webGl:renderer"] == "Old GPU" and "Nope" in notes[0]


@pytest.mark.parametrize(
    ("canvas", "webgl", "enabled", "overrides"),
    [
        ("noise", "noise", True, "-AllTargets,+CanvasRandomization,+WebGLRandomization"),
        ("noise", "real", True, "-AllTargets,+CanvasRandomization"),
        ("real", "noise", True, "-AllTargets,+WebGLRandomization"),
        ("real", "real", False, ""),
    ],
)
def test_noise_prefs(canvas, webgl, enabled, overrides):
    _, prefs, _ = run({"canvas": item(canvas), "webgl_noise": item(webgl)})
    assert prefs["privacy.fingerprintingProtection"] is enabled
    assert prefs["privacy.fingerprintingProtection.overrides"] == overrides


def test_audio_modes():
    assert run({"audio": item("noise")})[0]["audio:seed"] == 12345
    assert run({"audio": item("real")})[0]["audio:seed"] == 0


def test_webrtc_modes():
    config, prefs, _ = run(ip="203.0.113.7", proxy=True)
    assert config["webrtc:ipv4"] == "203.0.113.7" and prefs["network.dns.disableIPv6"] is True
    assert prefs["network.proxy.allow_hijacking_localhost"] is True
    config, prefs, _ = run(ip="2001:db8::7")
    assert config["webrtc:ipv6"] == "2001:db8::7" and prefs["network.dns.disableIPv6"] is False
    assert not any(
        k.startswith("webrtc:") for k in run()[0]
    )  # mask without an IP: nothing to claim
    config, _, _ = run({"webrtc": item("custom", "198.51.100.1")}, ip="203.0.113.7")
    assert config["webrtc:ipv4"] == "198.51.100.1"
    config, prefs, _ = run({"webrtc": item("real")}, ip="203.0.113.7")
    assert not any(k.startswith("webrtc:") for k in config)
    assert (
        prefs["media.peerconnection.enabled"] is True and prefs["network.dns.disableIPv6"] is False
    )
    config, prefs, _ = run({"webrtc": item("off")}, ip="203.0.113.7")
    assert not any(k.startswith("webrtc:") for k in config)
    assert prefs["media.peerconnection.enabled"] is False


def test_timezone_modes():
    assert run(geo=GEO)[0]["timezone"] == "Europe/Paris"
    assert "timezone" not in run()[0]
    assert run({"timezone": item("custom", "Asia/Tokyo")}, geo=GEO)[0]["timezone"] == "Asia/Tokyo"
    assert "timezone" not in run({"timezone": item("real")}, geo=GEO)[0]


def test_language_modes():
    config, prefs, _ = run({"language": item("mask")}, geo=GEO)
    assert (config["locale:language"], config["locale:region"]) == ("fr", "FR")
    assert prefs["intl.locale.requested"] in ("fr-FR", "fr-Latn-FR")
    config, prefs, _ = run({"language": item("custom", "de-DE")}, geo=GEO)
    assert (config["locale:language"], config["locale:region"]) == ("de", "DE")
    assert prefs["intl.locale.requested"] in ("de-DE", "de-Latn-DE")
    config, _, _ = run({"language": item("custom", "de-DE,en-US")})
    assert config["locale:all"] == "de-DE, en-US"
    config, prefs, _ = run({"language": item("real")}, geo=GEO)
    assert not any(k.startswith("locale:") for k in config) and prefs["intl.locale.requested"] == ""
    config, prefs, _ = run({"language": item("mask")})
    assert (
        not any(k.startswith("locale:") for k in config)
        and prefs["intl.locale.requested"] == "en-US"
    )


def test_geolocation_and_permission():
    config, prefs, _ = run({"geolocation": item("mask")}, geo=GEO)
    assert config["geolocation:latitude"] == 48.85 and prefs["permissions.default.geo"] == 1
    config, _, _ = run(
        {"geolocation": item("custom", {"latitude": 1.5, "longitude": 2.5, "accuracy": 9})}
    )
    assert (config["geolocation:latitude"], config["geolocation:longitude"]) == (1.5, 2.5)
    assert config["geolocation:accuracy"] == 9
    config, _, _ = run({"geolocation": item("real")}, geo=GEO)
    assert not any(k.startswith("geolocation:") for k in config)
    config, prefs, _ = run({"geo_permission": item("prompt")}, geo=GEO)
    assert prefs["permissions.default.geo"] == 0 and "geolocation:latitude" in config
    config, prefs, _ = run({"geo_permission": item("block")}, geo=GEO)
    assert prefs["permissions.default.geo"] == 2
    assert not any(
        k.startswith("geolocation:") for k in config
    )  # spoofed coordinates bypass a deny


def test_screen_modes():
    config, _, _ = run({"screen": item("custom", "1600x900")})
    assert (config["screen.width"], config["screen.height"]) == (1600, 900)
    assert (config["screen.availWidth"], config["screen.availHeight"]) == (
        1600,
        860,
    )  # taskbar kept
    assert config["window.outerWidth"] <= 1600 and config["window.outerHeight"] <= 860
    config, _, _ = run({"screen": item("custom", "2560x1440")})
    assert config["screen.availHeight"] == 1400
    config, _, _ = run({"screen": item("real")})
    assert not any(k.startswith(("screen.", "window.")) for k in config)
    assert run({"screen": item("mask")})[0]["screen.width"] == 1920


def test_fonts_modes():
    assert run({"fonts": item("custom", ["Only"])})[0]["fonts"] == ["Only"]
    assert "fonts" not in run({"fonts": item("real")})[0]
    assert run()[0]["fonts"] == DEVICE["fonts"]


def test_media_devices_modes():
    config, _, _ = run({"media_devices": item("real")})
    assert config["mediaDevices:enabled"] is False
    config, _, _ = run({"media_devices": item("off")})
    assert config["mediaDevices:enabled"] is True
    assert [config[f"mediaDevices:{k}"] for k in ("micros", "webcams", "speakers")] == [0, 0, 0]
    assert (
        config["mediaDevices:microphoneLabels"] == [] and config["mediaDevices:speakerGroups"] == []
    )
    custom = {"micros": 2, "webcams": 0, "speakers": 3}
    config, _, _ = run({"media_devices": item("custom", custom)})
    assert config["mediaDevices:micros"] == 2 and config["mediaDevices:webcams"] == 0
    assert config["mediaDevices:microphoneLabels"] == ["Mic", "Microphone 2"]
    assert len(config["mediaDevices:microphoneGroups"]) == 2
    assert (
        len(config["mediaDevices:speakerLabels"]) == len(config["mediaDevices:speakerGroups"]) == 3
    )
    assert config["mediaDevices:webcamLabels"] == []
    assert run()[0]["mediaDevices:micros"] == 1


def test_voices_modes():
    config, _, _ = run({"voices": item("off")})
    assert config["voices"] == [] and config["voices:blockIfNotDefined"] is True
    config, _, _ = run({"voices": item("real")})
    assert "voices" not in config and config["voices:blockIfNotDefined"] is False
    assert run()[0]["voices"] == DEVICE["voices"]


def test_port_scan_modes():
    _, prefs, _ = run({"port_scan": item("custom", ["127.0.0.1", "intranet.test"])}, proxy=True)
    assert prefs["network.lna.skip-domains"] == "127.0.0.1,intranet.test"
    assert prefs["network.lna.enabled"] is True and prefs["network.lna.blocking"] is True
    assert prefs["network.lna.websocket.enabled"] is True
    assert prefs["network.proxy.allow_hijacking_localhost"] is True
    _, prefs, _ = run({"port_scan": item("real")}, proxy=True)
    assert prefs["network.lna.enabled"] is False
    assert prefs["network.proxy.allow_hijacking_localhost"] is False
    _, prefs, _ = run(proxy=True)
    assert (
        prefs["network.lna.enabled"] is True
        and prefs["network.proxy.allow_hijacking_localhost"] is True
    )


def test_launch_os():
    assert fpsettings.launch_os(fpsettings.defaults("macos"), "macos") == "macos"
    real = fpsettings.normalize({"os": item("real")}, "macos")
    assert fpsettings.launch_os(real, "macos") == fpsettings.HOST_OS


def test_needs_ip():
    assert fpsettings.needs_ip(fpsettings.defaults("windows"))
    off = {n: item("real") for n in ("webrtc", "timezone", "geolocation", "language")}
    assert not fpsettings.needs_ip(fpsettings.normalize(off, "windows"))


# --- check ---------------------------------------------------------------------


def warnings_for(partial=None, os="windows", host="windows", proxy=False):
    return fpsettings.check(fpsettings.normalize(partial, os), None, os, host, proxy)


def test_check_clean_by_default():
    assert warnings_for() == []


def test_check_user_agent_and_platform():
    mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0) Gecko/20100101 Firefox/150.0"
    assert "different OS" in warnings_for({"user_agent": item("custom", mac)})[0]
    assert warnings_for({"user_agent": item("custom", mac)}, os="macos", host="macos") == []
    assert "platform" in warnings_for({"platform": item("custom", "MacIntel")})[0]
    assert warnings_for({"platform": item("custom", "Win32")}) == []


def test_check_gpu():
    gpu = devices.gpus("windows")[0]
    assert warnings_for({"webgl_meta": item("custom", gpu)}) == []
    assert (
        "GPU" in warnings_for({"webgl_meta": item("custom", {"vendor": "a", "renderer": "b"})})[0]
    )


def test_check_real_values_on_another_os():
    real = {n: item("real") for n in ("user_agent", "platform", "fonts", "webgl_meta", "screen")}
    assert warnings_for(real) == []
    assert len(warnings_for(real, os="linux")) == 5


def test_check_custom_screen_against_host_scale(monkeypatch):
    monkeypatch.setattr(devices, "host_dpr", lambda: 2.0)
    assert "panel" in warnings_for({"screen": item("custom", "2560x1440")})[0]
    assert not any("panel" in w for w in warnings_for({"screen": item("custom", "1920x1080")}))


def test_check_misc():
    assert any(
        "cores" in w
        for w in warnings_for({"hardware_concurrency": item("custom", 4)}, host="macos")
    )
    assert warnings_for({"hardware_concurrency": item("custom", 4)}) == []
    assert "prompt" in warnings_for({"geo_permission": item("prompt")})[0]
    assert warnings_for({"geo_permission": item("prompt"), "geolocation": item("real")}) == []
    assert "media devices" in warnings_for({"media_devices": item("real")})[0]
    real = {n: item("real") for n in ("webrtc", "timezone", "language")}
    assert warnings_for(real) == []
    assert len(warnings_for(real, proxy=True)) == 3


def test_options():
    opts = fpsettings.options("windows")
    assert opts["gpus"] == devices.gpus("windows") and opts["screens"] == devices.screens("windows")
    assert "Arial" in opts["fonts"]
    assert opts["items"]["canvas"] == {"modes": ["noise", "real"], "default": item("noise")}
    assert opts["items"]["os"]["default"] == item("custom", "windows")
    assert set(opts["items"]) == set(fpsettings.ITEMS)


# --- Profiles on disk -----------------------------------------------------------


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_profiles_file_without_settings_loads_legacy(workdir):
    (workdir / "profiles.json").write_text(
        json.dumps(
            {
                "a": {"name": "a", "os_type": "macos"},
                "b": {"name": "b", "os_type": "macos", "timezone": "Asia/Tokyo", "locale": "ja-JP"},
            }
        ),
        encoding="utf-8",
    )
    profiles = ProfileManager().profiles
    assert profiles["a"].fingerprint["language"] == item("mask")
    assert profiles["a"].locale is None
    assert profiles["b"].fingerprint["timezone"] == item("custom", "Asia/Tokyo")
    assert profiles["b"].fingerprint["language"] == item("custom", "ja-JP")


def test_a_bad_item_in_profiles_file_does_not_lose_the_profile(workdir):
    (workdir / "profiles.json").write_text(
        json.dumps(
            {
                "a": {
                    "name": "a",
                    "fingerprint": {"screen": item("custom", "bad"), "canvas": item("real")},
                }
            }
        ),
        encoding="utf-8",
    )
    fp = ProfileManager().profiles["a"].fingerprint
    assert fp["canvas"] == item("real") and fp["screen"] == item("mask")


def test_saved_reads_the_profile_for_the_subprocesses(workdir):
    pm = ProfileManager()
    pm.add_profile("p", "", "windows", fingerprint={"canvas": item("real")})
    assert fpsettings.saved("p", "windows")["canvas"] == item("real")
    assert fpsettings.saved("missing", "windows") == fpsettings.defaults("windows") | {
        "language": item("mask")
    }


def test_timezone_and_language_stay_in_step(workdir):
    pm = ProfileManager()
    pm.add_profile("p", "", "windows", "Asia/Tokyo", "ja-JP")
    p = pm.profiles["p"]
    assert p.fingerprint["timezone"] == item("custom", "Asia/Tokyo")
    assert p.fingerprint["language"] == item("custom", "ja-JP")
    # Settings -> profile fields
    pm.update_profile("p", "p", "", "windows", "Asia/Tokyo", "ja-JP", {"language": item("mask")})
    assert p.locale is None and p.timezone == "Asia/Tokyo"
    pm.update_profile("p", "p", "", "windows", "Asia/Tokyo", None, {"timezone": item("real")})
    assert p.timezone is None and p.fingerprint["timezone"] == item("real")
    # Profile fields -> settings
    pm.update_profile("p", "p", "", "windows", "Europe/Berlin", "de-DE")
    assert p.fingerprint["timezone"] == item("custom", "Europe/Berlin")
    pm.update_profile("p", "p", "", "windows", None, None)
    assert p.fingerprint["timezone"] == item("mask") and p.fingerprint["language"] == item("mask")
    # Survives a reload
    assert ProfileManager().profiles["p"].fingerprint == p.fingerprint


def test_new_profile_keeps_the_default_language_without_pinning_locale(workdir):
    pm = ProfileManager()
    pm.add_profile("p", "", "windows")
    assert pm.profiles["p"].locale is None
    assert pm.profiles["p"].fingerprint["language"] == item("custom", "en-US")


def test_os_change_updates_the_os_item(workdir):
    pm = ProfileManager()
    pm.add_profile("p", "", "windows")
    pm.update_profile("p", "p", "", "linux")
    assert pm.profiles["p"].fingerprint["os"] == item("custom", "linux")


def test_export_import_round_trip_and_tolerance(workdir):
    import zipfile

    pm = ProfileManager()
    pm.add_profile("p", "", "windows", fingerprint={"hardware_concurrency": item("custom", 6)})
    ok, zip_path = pm.export_profile("p", str(workdir), include_data=False)
    assert ok
    pm.delete_profile("p")
    ok, name = pm.import_profile(zip_path)
    assert ok and pm.profiles[name].fingerprint["hardware_concurrency"] == item("custom", 6)

    broken = workdir / "broken.zip"
    with zipfile.ZipFile(broken, "w") as z:
        z.writestr(
            "profile.json",
            json.dumps(
                {"name": "q", "fingerprint": {"canvas": item("bogus"), "audio": item("real")}}
            ),
        )
    ok, name = pm.import_profile(str(broken))
    assert ok and pm.profiles["q"].fingerprint["canvas"] == item("noise")
    assert pm.profiles["q"].fingerprint["audio"] == item("real")


# --- REST ----------------------------------------------------------------------


@pytest.fixture
def client(workdir):
    return TestClient(create_app(Container()), base_url="http://127.0.0.1")


API = "/api/v1"


def test_rest_round_trip(client, workdir):
    r = client.post(f"{API}/profiles", json={"name": "r1", "os_type": "windows"})
    assert r.status_code == 201 and r.json()["engine"] == "camoufox"

    r = client.get(f"{API}/profiles/r1/fingerprint")
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] is False
    assert all("fonts" in w for w in body["warnings"])  # only the cross-OS font note on a Mac
    assert body["settings"]["canvas"] == item("noise")

    r = client.put(
        f"{API}/profiles/r1/fingerprint/settings",
        json={
            "hardware_concurrency": item("custom", 8),
            "webrtc": item("off"),
            "port_scan": item("custom", ["127.0.0.1"]),
            "geo_permission": item("prompt"),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["settings"]["hardware_concurrency"] == item("custom", 8)
    assert body["applies_on_next_launch"] is False
    assert any("prompt" in w for w in body["warnings"])

    got = client.get(f"{API}/profiles/r1/fingerprint").json()
    assert got["settings"]["webrtc"] == item("off") and got["settings"]["canvas"] == item("noise")
    assert ProfileManager().profiles["r1"].fingerprint["webrtc"] == item("off")


def test_rest_rejects_bad_settings(client):
    client.post(f"{API}/profiles", json={"name": "r2"})
    for bad in ({"canvas": item("mask")}, {"nope": item("mask")}, {"screen": item("custom", "x")}):
        r = client.put(f"{API}/profiles/r2/fingerprint/settings", json=bad)
        assert r.status_code == 400, bad
    assert client.put(f"{API}/profiles/ghost/fingerprint/settings", json={}).status_code == 404
    r = client.post(f"{API}/profiles", json={"name": "r3", "fingerprint": {"canvas": item("x")}})
    assert r.status_code == 400
    assert client.get(f"{API}/profiles/r3").status_code == 404


def test_rest_create_and_patch_carry_settings(client):
    r = client.post(
        f"{API}/profiles",
        json={"name": "r4", "fingerprint": {"timezone": item("custom", "Europe/Berlin")}},
    )
    assert r.status_code == 201 and r.json()["timezone"] == "Europe/Berlin"
    r = client.patch(
        f"{API}/profiles/r4", json={"fingerprint": {"language": item("custom", "de-DE")}}
    )
    assert r.status_code == 200 and r.json()["locale"] == "de-DE"
    r = client.patch(f"{API}/profiles/r4", json={"timezone": "", "locale": ""})
    assert r.status_code == 200 and r.json()["timezone"] is None and r.json()["locale"] is None
    fp = client.get(f"{API}/profiles/r4/fingerprint").json()["settings"]
    assert fp["timezone"] == item("mask") and fp["language"] == item("mask")
    r = client.patch(f"{API}/profiles/r4", json={"fingerprint": {"canvas": item("mask")}})
    assert r.status_code == 400


def test_rest_os_setting_changes_the_profile_os(client):
    client.post(f"{API}/profiles", json={"name": "r5", "os_type": "windows"})
    r = client.put(f"{API}/profiles/r5/fingerprint/settings", json={"os": item("custom", "linux")})
    assert r.status_code == 200 and r.json()["settings"]["os"] == item("custom", "linux")
    assert client.get(f"{API}/profiles/r5").json()["os_type"] == "linux"


def test_rest_regenerate_removes_the_device_and_keeps_settings(client, workdir):
    client.post(f"{API}/profiles", json={"name": "r6"})
    client.put(f"{API}/profiles/r6/fingerprint/settings", json={"audio": item("real")})
    (workdir / "camoufox_data" / "r6").mkdir(parents=True, exist_ok=True)
    (workdir / "camoufox_data" / "r6" / "fingerprint.json").write_text("{}", encoding="utf-8")
    assert client.post(f"{API}/profiles/r6/fingerprint/regenerate").status_code == 200
    assert not (workdir / "camoufox_data" / "r6" / "fingerprint.json").exists()
    assert client.get(f"{API}/profiles/r6/fingerprint").json()["settings"]["audio"] == item("real")
    assert client.post(f"{API}/profiles/ghost/fingerprint/regenerate").status_code == 404


def test_rest_options(client):
    r = client.get(f"{API}/fingerprint/options", params={"os": "macos"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"gpus", "screens", "fonts", "items"}
    assert body["items"]["canvas"]["modes"] == ["noise", "real"]
    assert client.get(f"{API}/fingerprint/options", params={"os": "beos"}).status_code == 400


def test_rest_options_need_the_token(client, monkeypatch):
    from src.api import app, auth

    monkeypatch.setattr(auth, "API_TOKEN", "t" * 32)
    monkeypatch.setattr(app, "API_TOKEN", "t" * 32)
    assert client.get(f"{API}/fingerprint/options").status_code == 401


# --- A real launch_options run ---------------------------------------------------


def test_build_launch_with_the_real_browser(tmp_path):
    from camoufox.exceptions import CamoufoxNotInstalled
    from camoufox.pkgman import installed_verstr

    try:
        major = installed_verstr().split(".")[0]
    except CamoufoxNotInstalled:
        pytest.skip("Camoufox browser not fetched")
    logs = []
    settings = fpsettings.normalize({"hardware_concurrency": item("custom", 6)}, "windows")
    opts = fpsettings.build_launch(str(tmp_path), settings, "windows", log=logs.append)
    config = fingerprint.decode_config(opts["env"])
    assert config["navigator.hardwareConcurrency"] == 6
    assert f"Firefox/{major}.0" in config["navigator.userAgent"]
    assert "Windows" in config["navigator.userAgent"]
    assert config["locale:language"] == "en" and config["audio:seed"]
    assert "CAMOU_PREFS_1" in opts["env"]
    assert opts["firefox_user_prefs"]["privacy.fingerprintingProtection"] is True
    assert opts["user_data_dir"] == str(tmp_path)

    again = fpsettings.build_launch(str(tmp_path), settings, "windows", log=logs.append)
    assert fingerprint.decode_config(again["env"]) == config  # the device is frozen
    saved = json.loads((tmp_path / "fingerprint.json").read_text(encoding="utf-8"))
    assert saved["version"] == 2 and saved["os"] == "windows" and saved["source"]
    assert not any(
        k.startswith(("addons", "locale:", "timezone", "geolocation:")) for k in saved["device"]
    )


def test_cross_os_fonts_on_a_mac():
    config, prefs = {"fonts": ["Arial", "Segoe UI"]}, {}
    fpsettings.cross_os_fonts(config, prefs, "windows", "macos", "mask")
    assert prefs["gfx.bundled-fonts.activate"] == 0
    assert config["fonts"][-1] == fpsettings.FALLBACK_FONT
    assert prefs["font.name-list.sans-serif.zh-CN"].startswith("Microsoft YaHei")
    assert prefs["font.name-list.sans-serif.zh-CN"].endswith(fpsettings.FALLBACK_FONT)
    for os_, host, fonts in (
        ("macos", "macos", "mask"),
        ("windows", "windows", "mask"),
        ("windows", "macos", "real"),
    ):
        config, prefs = {"fonts": ["Arial"]}, {}
        fpsettings.cross_os_fonts(config, prefs, os_, host, fonts)
        assert prefs == {} and config == {"fonts": ["Arial"]}


def test_api_replies_stay_english_when_the_ui_is_chinese(client, monkeypatch):
    from src.core import strings

    monkeypatch.setattr(strings, "_lang", "zh-CN")
    assert (
        strings.get_string("validation_empty_name")
        != strings.STRINGS["en"]["validation_empty_name"]
    )
    r = client.post(f"{API}/profiles", json={"name": "   ", "os_type": "windows"})
    assert r.status_code >= 400
    assert not any("一" <= c <= "鿿" for c in r.text), r.text
