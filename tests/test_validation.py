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
    ["", "1.2.3.4:8080", "http://h.com:80", "socks5://u:p@1.2.3.4:1080", "https://proxy.vn:443"],
)
def test_valid_proxies(proxy):
    assert validate_proxy_format(proxy)[0]


@pytest.mark.parametrize("proxy", ["nohost", "ftp://h:21", "h:0", "h:70000", "u:p@h"])
def test_invalid_proxies(proxy):
    assert not validate_proxy_format(proxy)[0]


def test_parse_proxy_with_auth():
    assert parse_proxy("socks5://user:pass@1.2.3.4:1080") == {
        "server": "socks5://1.2.3.4:1080",
        "username": "user",
        "password": "pass",
    }


def test_parse_proxy_defaults_to_http():
    assert parse_proxy("1.2.3.4:8080") == {"server": "http://1.2.3.4:8080"}


def test_parse_proxy_empty():
    assert parse_proxy("") is None
