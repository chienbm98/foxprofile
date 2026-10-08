import asyncio
import json
import types
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.profile import manager as manager_module
from src.services.profile.transfer import import_from_zip
from src.services.proxy import geo_check
from src.services.proxy.geo_check import SourceResult, check_geo, compare
from src.utils.validation import validate_locale, validate_timezone


@pytest.mark.parametrize("value", ["", "Asia/Ho_Chi_Minh", "Europe/Paris", "UTC"])
def test_valid_timezones(value):
    assert validate_timezone(value)[0]


@pytest.mark.parametrize("value", ["Asia/Hanoi", "GMT+7", "../etc/passwd", "asia/ho_chi_minh"])
def test_invalid_timezones(value):
    assert not validate_timezone(value)[0]


@pytest.mark.parametrize("value", ["", "vi-VN", "fr-FR", "zh-Hant-TW", "es-419"])
def test_valid_locales(value):
    assert validate_locale(value)[0]


@pytest.mark.parametrize("value", ["vi", "vi_VN", "VN", "zz-ZZ", "vi-VN, en-US"])
def test_invalid_locales(value):
    assert not validate_locale(value)[0]


def test_runner_overrides_only_what_is_pinned():
    from src.services.browser.runner import geo_overrides

    assert geo_overrides("", "") == {}
    assert geo_overrides("Asia/Ho_Chi_Minh", "") == {"config": {"timezone": "Asia/Ho_Chi_Minh"}}
    assert geo_overrides("", "vi-VN") == {"locale": "vi-VN"}


def test_manager_persists_timezone_and_locale(tmp_path, monkeypatch):
    monkeypatch.setattr(manager_module, "PROFILES_FILE", str(tmp_path / "profiles.json"))
    monkeypatch.setattr(manager_module, "DATA_DIR", str(tmp_path / "data"))
    pm = manager_module.ProfileManager()
    pm.add_profile("p", "", "windows", "Asia/Ho_Chi_Minh", "vi-VN")

    reloaded = manager_module.ProfileManager().profiles["p"]
    assert (reloaded.timezone, reloaded.locale) == ("Asia/Ho_Chi_Minh", "vi-VN")

    pm.update_profile("p", "p", "", "windows", "", "")
    reloaded = manager_module.ProfileManager().profiles["p"]
    assert (reloaded.timezone, reloaded.locale) == (None, None)


def test_import_drops_invalid_geo_values(tmp_path):
    zip_path = tmp_path / "p.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(
            "profile.json",
            json.dumps({"name": "p", "timezone": "Mars/Base", "locale": "fr-FR"}),
        )
    ok, profile = import_from_zip(str(zip_path), str(tmp_path / "data"))
    assert ok and profile.timezone is None and profile.locale == "fr-FR"


def _codes(warnings):
    return [w.code for w in warnings]


def test_compare_flags_disagreeing_sources():
    sources = [
        SourceResult("cloudflare", ip="2001:db8::1", country="FR"),
        SourceResult("ipinfo", ip="203.0.113.4", country="DE", timezone="Europe/Berlin"),
        SourceResult(
            "ip-api", ip="203.0.113.4", country="FR", timezone="Europe/Paris", hosting=True
        ),
        SourceResult("broken", error="timeout"),
    ]
    warnings = compare("203.0.113.4", "FR", "Europe/Paris", None, False, sources)
    assert _codes(warnings) == ["ip_differs", "country_mismatch", "timezone_mismatch", "hosting"]
    assert warnings[1].params == {"source": "ipinfo", "got": "DE", "expected": "FR"}


def test_compare_ignores_same_family_ip_changes_and_checks_pinned_locale():
    sources = [SourceResult("cloudflare", ip="203.0.113.5", country="FR")]
    assert compare("203.0.113.4", "FR", "Europe/Paris", "fr-FR", True, sources) == []
    assert _codes(compare("203.0.113.4", "FR", "Europe/Paris", "en-US", True, sources)) == [
        "locale_country"
    ]


@pytest.fixture
def fake_lookups(monkeypatch):
    monkeypatch.setattr(geo_check, "_exit_ip", lambda proxy: "198.51.100.7")
    monkeypatch.setattr(
        geo_check, "_camoufox_geo", lambda ip: ("VN", "Asia/Bangkok", "vi-VN", 0.98)
    )
    monkeypatch.setattr(
        geo_check,
        "_SOURCES",
        {
            "ipinfo": lambda proxies: SourceResult(
                "ipinfo", ip="198.51.100.7", country="VN", timezone="Asia/Ho_Chi_Minh"
            ),
            "ip-api": lambda proxies: (_ for _ in ()).throw(OSError("unreachable")),
        },
    )


def test_check_geo_automatic(fake_lookups):
    r = check_geo(None)
    assert (r.exit_ip, r.country, r.timezone, r.timezone_pinned) == (
        "198.51.100.7",
        "VN",
        "Asia/Bangkok",
        False,
    )
    assert r.sources[1].error == "OSError: unreachable"
    assert _codes(r.warnings) == ["timezone_mismatch", "locale_random"]
    assert r.warnings[1].params == {"suggested": "vi-VN", "share": 98}


def test_check_geo_pinned_values_clear_the_warnings(fake_lookups):
    r = check_geo(None, "Asia/Ho_Chi_Minh", "vi-VN")
    assert r.timezone == "Asia/Ho_Chi_Minh" and r.timezone_pinned and r.locale_pinned
    assert r.auto_timezone == "Asia/Bangkok"
    assert r.warnings == []


def test_check_geo_reports_unreachable_exit(monkeypatch, fake_lookups):
    def fail(proxy):
        raise OSError("proxy down")

    monkeypatch.setattr(geo_check, "_exit_ip", fail)
    r = check_geo("http://127.0.0.1:9")
    assert r.exit_ip is None and r.error == "OSError: proxy down"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from src.api.routes.profiles import router as profiles_router
    from src.api.routes.proxy import router as proxy_router

    monkeypatch.setattr(manager_module, "PROFILES_FILE", str(tmp_path / "profiles.json"))
    monkeypatch.setattr(manager_module, "DATA_DIR", str(tmp_path / "data"))
    app = FastAPI()
    app.state.container = types.SimpleNamespace(
        profile_manager=manager_module.ProfileManager(),
        browser_launcher=types.SimpleNamespace(is_running=lambda name: False),
        event_bus=types.SimpleNamespace(emit=lambda: None),
    )
    app.include_router(profiles_router)
    app.include_router(proxy_router)
    return TestClient(app)


def test_api_create_and_clear_geo(client):
    r = client.post("/profiles", json={"name": "p", "timezone": "Europe/Paris", "locale": "fr-FR"})
    assert r.status_code == 201
    assert (r.json()["timezone"], r.json()["locale"]) == ("Europe/Paris", "fr-FR")

    # Unrelated updates keep the pinned values; "" switches back to automatic.
    assert (
        client.patch("/profiles/p", json={"os_type": "linux"}).json()["timezone"] == "Europe/Paris"
    )
    r = client.patch("/profiles/p", json={"timezone": "", "locale": ""})
    assert (r.json()["timezone"], r.json()["locale"]) == (None, None)


@pytest.mark.parametrize("body", [{"timezone": "Paris"}, {"locale": "french"}])
def test_api_rejects_bad_geo(client, body):
    assert client.post("/profiles", json={"name": "p", **body}).status_code == 400
    client.post("/profiles", json={"name": "q"})
    assert client.patch("/profiles/q", json=body).status_code == 400


def test_api_ip_check(client, fake_lookups):
    client.post("/profiles", json={"name": "p", "timezone": "Asia/Ho_Chi_Minh"})
    data = client.get("/profiles/p/ip-check").json()
    assert data["timezone"] == "Asia/Ho_Chi_Minh" and data["timezone_pinned"]
    assert [w["code"] for w in data["warnings"]] == ["locale_random"]
    assert data["warnings"][0]["message"]

    r = client.post("/proxy/geo-check", json={"proxy": None, "locale": "vi-VN"})
    assert [w["code"] for w in r.json()["warnings"]] == ["timezone_mismatch"]
    assert client.post("/proxy/geo-check", json={"timezone": "nope"}).status_code == 400


def test_short_error_reports_root_cause_without_credentials():
    try:
        try:
            raise ConnectionRefusedError("refused by http://bob:S3cret@10.0.0.1:8080")
        except ConnectionRefusedError as inner:
            raise RuntimeError("Max retries exceeded with url ... (long boilerplate)") from inner
    except RuntimeError as e:
        text = geo_check._short_error(e)
    assert text.startswith("ConnectionRefusedError") and "S3cret" not in text and "***" in text


def test_compare_skips_numeric_regions_and_cloudflare_pseudo_countries():
    sources = [SourceResult("cloudflare", ip="203.0.113.4", country="XX")]
    assert compare("203.0.113.4", "MX", "America/Mexico_City", "es-419", True, sources) == []


def test_check_geo_gives_up_on_a_hanging_exit_lookup(monkeypatch, fake_lookups):
    import threading
    import time

    release = threading.Event()
    monkeypatch.setattr(geo_check, "_DEADLINE", 0.2)
    monkeypatch.setattr(geo_check, "_exit_ip", lambda proxy: release.wait(5) or "192.0.2.1")
    started = time.monotonic()
    r = check_geo(None)
    release.set()
    assert r.exit_ip is None and "0.2s" in r.error
    assert time.monotonic() - started < 2


def test_manager_drops_invalid_stored_values(tmp_path, monkeypatch):
    store = tmp_path / "profiles.json"
    store.write_text(json.dumps({"p": {"name": "p", "timezone": "Paris", "locale": "vi-VN"}}))
    monkeypatch.setattr(manager_module, "PROFILES_FILE", str(store))
    monkeypatch.setattr(manager_module, "DATA_DIR", str(tmp_path / "data"))
    profile = manager_module.ProfileManager().profiles["p"]
    assert (profile.timezone, profile.locale) == (None, "vi-VN")


def test_spawn_passes_timezone_and_locale(monkeypatch):
    from src.models.profile import Profile
    from src.services.browser import process

    seen = {}
    monkeypatch.setattr(process.subprocess, "Popen", lambda args, **kw: seen.setdefault("a", args))
    process.spawn_browser(Profile("p", None, "linux", "Europe/Paris", None))
    assert seen["a"][2:] == ["p", "None", "linux", "Europe/Paris", ""]


@pytest.mark.parametrize(
    ("proxy", "expected"),
    [
        ("socks5://u:p@1.2.3.4:1080", "socks5h://u:p@1.2.3.4:1080"),
        ("SOCKS5://1.2.3.4:1080", "socks5h://1.2.3.4:1080"),
        ("socks4://1.2.3.4:1080", "socks4a://1.2.3.4:1080"),
        ("http://u:p@1.2.3.4:8080", "http://u:p@1.2.3.4:8080"),
        ("1.2.3.4:8080:u:p", "http://u:p@1.2.3.4:8080"),
        ("", None),
    ],
)
def test_lookups_resolve_dns_through_the_proxy(proxy, expected):
    assert geo_check.requests_proxy_url(proxy) == expected


def test_runner_looks_up_the_exit_ip_with_remote_dns(monkeypatch):
    from camoufox import ip

    from src.services.browser import runner

    seen = []
    monkeypatch.setattr(ip, "public_ip", lambda proxy=None: seen.append(proxy) or "5.6.7.8")
    assert runner.exit_ip("socks5://1.2.3.4:1080") == "5.6.7.8"
    assert runner.exit_ip("") == "5.6.7.8"
    assert seen == ["socks5h://1.2.3.4:1080", None]


def _fake_launch(monkeypatch, tmp_path, public_ip):
    from camoufox import ip

    from src.services.browser import runner

    seen = {}

    def camoufox(**config):
        seen.update(config)
        raise RuntimeError("stop after the launch options")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ip, "public_ip", public_ip)
    monkeypatch.setattr(runner, "AsyncCamoufox", camoufox)
    monkeypatch.setattr(runner, "load_or_create", lambda *_: {})
    return runner, seen


def test_runner_passes_the_looked_up_exit_ip_as_geoip(monkeypatch, tmp_path):
    asked = []
    runner, seen = _fake_launch(
        monkeypatch, tmp_path, lambda proxy=None: asked.append(proxy) or "5.6.7.8"
    )
    # spawn_browser passes str(None) for a profile without a proxy.
    asyncio.run(runner.run_browser("p", "None", "windows"))
    asyncio.run(runner.run_browser("p", "socks5://1.2.3.4:1080", "windows"))
    assert seen["geoip"] == "5.6.7.8"
    assert asked == [None, "socks5h://1.2.3.4:1080"]


def test_dead_proxy_reports_launch_failed(monkeypatch, tmp_path, capsys):
    from camoufox.exceptions import InvalidIP

    def public_ip(proxy=None):
        raise InvalidIP("Failed to get IP address")

    runner, _ = _fake_launch(monkeypatch, tmp_path, public_ip)
    assert asyncio.run(runner.run_browser("p", "socks5://1.2.3.4:1080", "windows")) == 1
    assert "LAUNCH_FAILED: InvalidIP: Failed to get IP address" in capsys.readouterr().out
