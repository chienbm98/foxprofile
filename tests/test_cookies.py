import json
import time

import pytest

from src.services.browser import cookies


def _ext_cookie(**overrides):
    base = {
        "domain": ".example.com",
        "hostOnly": False,
        "httpOnly": True,
        "name": "sid",
        "path": "/",
        "sameSite": "lax",
        "secure": True,
        "session": False,
        "expirationDate": 2_000_000_000,
        "value": "abc",
    }
    base.update(overrides)
    return base


def test_parse_extension_json():
    [c] = cookies.parse_cookies(json.dumps([_ext_cookie()]))
    assert c == {
        "name": "sid",
        "value": "abc",
        "domain": ".example.com",
        "path": "/",
        "httpOnly": True,
        "secure": True,
        "sameSite": "Lax",
        "expires": 2_000_000_000.0,
    }


def test_parse_host_only_keeps_bare_domain():
    [c] = cookies.parse_cookies(json.dumps([_ext_cookie(domain="app.example.com", hostOnly=True)]))
    assert c["domain"] == "app.example.com"


def test_parse_non_host_only_adds_leading_dot():
    [c] = cookies.parse_cookies(json.dumps([_ext_cookie(domain="example.com", hostOnly=False)]))
    assert c["domain"] == ".example.com"


def test_same_site_none_forces_secure():
    [c] = cookies.parse_cookies(json.dumps([_ext_cookie(sameSite="no_restriction", secure=False)]))
    assert c["sameSite"] == "None"
    assert c["secure"] is True


def test_session_cookie_gets_long_lifetime():
    [c] = cookies.parse_cookies(json.dumps([_ext_cookie(session=True, expirationDate=None)]))
    assert c["expires"] > time.time() + 300 * 24 * 3600


def test_parse_playwright_layout():
    pw = {
        "name": "a",
        "value": "1",
        "domain": ".x.com",
        "path": "/",
        "expires": 2_000_000_000,
        "httpOnly": False,
        "secure": False,
        "sameSite": "Strict",
    }
    [c] = cookies.parse_cookies(json.dumps({"cookies": [pw]}))
    assert c["sameSite"] == "Strict"
    assert c["expires"] == 2_000_000_000.0


def test_parse_skips_entries_without_name_or_domain():
    parsed = cookies.parse_cookies(json.dumps([{"value": "x"}, _ext_cookie()]))
    assert [c["name"] for c in parsed] == ["sid"]


def test_parse_invalid_json_raises():
    with pytest.raises(cookies.CookieError):
        cookies.parse_cookies("[not json")


def test_parse_netscape_with_http_only_and_session():
    text = (
        "# Netscape HTTP Cookie File\n"
        "#HttpOnly_.shop.vn\tTRUE\t/\tTRUE\t2000000000\ttoken\tt0k\n"
        ".shop.vn\tTRUE\t/\tFALSE\t0\tvisitor\txyz\n"
        "# a comment\n"
        "malformed line\n"
    )
    token, visitor = cookies.parse_cookies(text)
    assert token["httpOnly"] is True and token["secure"] is True
    assert token["expires"] == 2_000_000_000.0
    assert visitor["httpOnly"] is False
    assert visitor["expires"] > time.time()


def test_netscape_round_trip():
    source = [
        {
            "name": "a",
            "value": "1",
            "domain": ".x.com",
            "path": "/",
            "expires": 2_000_000_000,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        },
        {
            "name": "b",
            "value": "2",
            "domain": "y.com",
            "path": "/p",
            "expires": 2_000_000_000,
            "httpOnly": False,
            "secure": False,
            "sameSite": "Lax",
        },
    ]
    parsed = cookies.parse_cookies(cookies._to_netscape(source))
    assert [(c["name"], c["domain"], c["path"], c["httpOnly"]) for c in parsed] == [
        ("a", ".x.com", "/", True),
        ("b", "y.com", "/p", False),
    ]


def test_extension_json_round_trip():
    source = [
        {
            "name": "a",
            "value": "1",
            "domain": "y.com",
            "path": "/",
            "expires": -1,
            "httpOnly": False,
            "secure": True,
            "sameSite": "None",
        }
    ]
    [ext] = cookies._to_extension_json(source)
    assert ext["hostOnly"] is True and ext["session"] is True
    assert "expirationDate" not in ext
    assert ext["sameSite"] == "no_restriction"
    [back] = cookies.parse_cookies(json.dumps([ext]))
    assert back["domain"] == "y.com" and back["sameSite"] == "None"


def test_export_rejects_unknown_format():
    with pytest.raises(cookies.CookieError):
        cookies.export_cookies("p", "windows", "xml")


def test_non_numeric_expiry_is_treated_as_session():
    [c] = cookies.parse_cookies(json.dumps([_ext_cookie(expirationDate="session")]))
    assert c["expires"] > time.time() + 300 * 24 * 3600
