import pytest

from src.utils.proxy_parser import parse_proxy
from src.utils.validation import validate_profile_name, validate_proxy_format


@pytest.mark.parametrize("name", ["shop-01", "TikTok US 2", "ads_agency.3", "tài-khoản-1"])
def test_valid_profile_names(name):
    assert validate_profile_name(name) == (True, "")


@pytest.mark.parametrize(
    "name",
    ["", " lead", "trail ", "a/b", "a\\b", "x" * 65, "CON", "com1", ".", "..", "name."],
)
def test_invalid_profile_names(name):
    ok, msg = validate_profile_name(name)
    assert not ok and msg


@pytest.mark.parametrize(
    "proxy",
    [
        "",
        "1.2.3.4:8080",
        "http://h.com:80",
        "socks5://u:p@1.2.3.4:1080",
        "https://proxy.vn:443",
        "1.2.3.4:5062:user:secret",
        "socks5://1.2.3.4:1080:user:secret",
    ],
)
def test_valid_proxies(proxy):
    assert validate_proxy_format(proxy)[0]


@pytest.mark.parametrize(
    "proxy", ["nohost", "ftp://h:21", "h:0", "h:70000", "u:p@h", "1.2.3.4:5062:user:", "h:x:u:p"]
)
def test_invalid_proxies(proxy):
    assert not validate_proxy_format(proxy)[0]


def test_parse_proxy_with_auth():
    assert parse_proxy("socks5://user:pass@1.2.3.4:1080") == {
        "server": "socks5://1.2.3.4:1080",
        "username": "user",
        "password": "pass",
    }


def test_parse_proxy_host_port_user_pass():
    assert parse_proxy("1.2.3.4:5062:user:secret") == {
        "server": "http://1.2.3.4:5062",
        "username": "user",
        "password": "secret",
    }
    assert parse_proxy("socks5://1.2.3.4:1080:user:secret")["server"] == "socks5://1.2.3.4:1080"


def test_parse_proxy_defaults_to_http():
    assert parse_proxy("1.2.3.4:8080") == {"server": "http://1.2.3.4:8080"}


def test_parse_proxy_empty():
    assert parse_proxy("") is None


# ---------------------------------------------------------------------------
# Proxy host-length and port-range bounds (fix 2)
# ---------------------------------------------------------------------------


def test_proxy_host_exactly_253_chars_valid():
    host = "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 61  # 253 chars
    assert len(host) == 253
    ok, _ = validate_proxy_format(f"{host}:8080")
    assert ok


def test_proxy_host_254_chars_rejected():
    host = "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 62  # 254 chars
    assert len(host) == 254
    ok, _ = validate_proxy_format(f"{host}:8080")
    assert not ok


def test_proxy_host_9000_chars_rejected():
    host = "x" * 9000
    ok, _ = validate_proxy_format(f"{host}:8080")
    assert not ok


@pytest.mark.parametrize("port", ["0", "99999"])
def test_proxy_port_out_of_range_rejected(port):
    ok, _ = validate_proxy_format(f"192.0.2.1:{port}")
    assert not ok
