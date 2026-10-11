"""The locale a profile keeps for the country of its exit IP."""

import json

import pytest

from chrome_engine.geo import GEO_LOCALE_FILE, remembered_locale


def test_first_locale_is_kept_for_the_country(tmp_path):
    assert remembered_locale(tmp_path, "US", "es-US") == "es-US"
    # Later lookups pick at random again; the profile keeps its first locale.
    assert remembered_locale(tmp_path, "US", "en-US") == "es-US"
    saved = json.loads((tmp_path / GEO_LOCALE_FILE).read_text(encoding="utf-8"))
    assert saved == {"country": "US", "locale": "es-US"}


def test_new_country_replaces_the_locale(tmp_path):
    remembered_locale(tmp_path, "US", "en-US")
    assert remembered_locale(tmp_path, "VN", "vi-VN") == "vi-VN"
    assert remembered_locale(tmp_path, "VN", "en-VN") == "vi-VN"


def test_unknown_country_is_not_remembered(tmp_path):
    assert remembered_locale(tmp_path, None, "en-US") == "en-US"
    assert not (tmp_path / GEO_LOCALE_FILE).exists()


@pytest.mark.parametrize(
    "content",
    ["{broken", "[]", '{"country": "US", "locale": 5}', '{"country": "US", "locale": "x/../y"}'],
)
def test_unusable_file_is_replaced(tmp_path, content):
    (tmp_path / GEO_LOCALE_FILE).write_text(content, encoding="utf-8")
    assert remembered_locale(tmp_path, "US", "en-US") == "en-US"
    assert remembered_locale(tmp_path, "US", "es-US") == "en-US"


@pytest.mark.parametrize("locale", ["en-US", "zh-Hant-TW", "es-419", "fil-PH"])
def test_real_locales_are_reused(tmp_path, locale):
    remembered_locale(tmp_path, "XX", locale)
    assert remembered_locale(tmp_path, "XX", "en-US") == locale


def test_same_file_name_as_the_app():
    from src.services.browser import fingerprint

    assert fingerprint.GEO_LOCALE_FILE == GEO_LOCALE_FILE
