import json

import pytest

from chrome_engine import persona as personas
from chrome_engine.persona import Persona, PersonaError


def test_generate_is_deterministic_per_seed_and_platform():
    a = personas.generate("windows", seed=12345)
    b = personas.generate("windows", seed=12345)
    assert a == b
    assert personas.generate("macos", seed=12345).platform == "macos"


def test_generate_varies_with_seed():
    values = {
        (p.platform_version, p.hardware_concurrency)
        for p in (personas.generate("windows", seed=s) for s in range(1, 200))
    }
    assert len(values) > 5


@pytest.mark.parametrize("platform", personas.PLATFORMS)
def test_generated_values_are_valid(platform):
    for seed in range(1, 100):
        p = personas.generate(platform, seed=seed)
        personas.validate(p)
        assert 1 <= p.seed <= personas.SEED_MAX


def test_random_seed_when_none():
    seeds = {personas.generate("linux").seed for _ in range(20)}
    assert len(seeds) > 15


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"seed": 0}, "seed"),
        ({"seed": 2**31}, "seed"),
        ({"platform": "android"}, "platform"),
        ({"platform_version": "15"}, "platform_version"),
        ({"brand": "Firefox"}, "brand"),
        ({"brand": "Edge", "platform": "linux", "platform_version": "6.8.0"}, "Edge"),
        ({"hardware_concurrency": 0}, "hardware_concurrency"),
        ({"hardware_concurrency": 128}, "hardware_concurrency"),
        ({"timezone": "Mars/Olympus"}, "timezone"),
        ({"locale": "english"}, "locale"),
    ],
)
def test_validation(changes, message):
    base = {"seed": 7, "platform": "windows", "platform_version": "15.0.0"}
    with pytest.raises(PersonaError, match=message):
        Persona(**{**base, **changes})


def test_to_args():
    p = Persona(
        seed=42,
        platform="macos",
        platform_version="15.6.1",
        brand="Edge",
        hardware_concurrency=10,
        timezone="Asia/Tokyo",
        locale="ja-JP",
    )
    assert p.to_args() == [
        "--fingerprint=42",
        "--fingerprint-platform=macos",
        "--fingerprint-platform-version=15.6.1",
        "--fingerprint-brand=Edge",
        "--fingerprint-hardware-concurrency=10",
        "--timezone=Asia/Tokyo",
        "--lang=ja-JP",
        "--accept-lang=ja-JP,ja,en-US,en",
    ]


def test_to_args_leaves_geo_to_the_ip():
    args = Persona(seed=1, platform="windows", platform_version="10.0.0").to_args()
    assert not any(a.startswith(("--timezone", "--lang", "--accept-lang")) for a in args)


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("vi-VN", "vi-VN,vi,en-US,en"),
        ("en-US", "en-US,en"),
        ("en-GB", "en-GB,en"),
        ("fr", "fr,en-US,en"),
    ],
)
def test_accept_languages(locale, expected):
    assert personas.accept_languages(locale) == expected


def test_with_geo_only_fills_open_fields():
    pinned = Persona(seed=1, platform="windows", platform_version="10.0.0", timezone="Europe/Paris")
    filled = pinned.with_geo("Asia/Tokyo", "ja-JP")
    assert filled.timezone == "Europe/Paris"
    assert filled.locale == "ja-JP"


def test_json_roundtrip_ignores_unknown_keys():
    p = personas.generate("windows", seed=99, locale="vi-VN")
    data = {**p.to_json(), "future_field": 1}
    assert Persona.from_json(data) == p


def test_load_or_create_persists(tmp_path):
    first = personas.load_or_create(tmp_path, "windows")
    assert personas.persona_path(tmp_path).is_file()
    assert personas.load_or_create(tmp_path, "windows") == first


def test_load_or_create_regenerates_when_os_changes(tmp_path):
    first = personas.load_or_create(tmp_path, "windows")
    second = personas.load_or_create(tmp_path, "macos")
    assert second.platform == "macos"
    assert personas.load(tmp_path) == second
    assert second != first


def test_overrides_keep_the_device(tmp_path):
    first = personas.load_or_create(tmp_path, "windows")
    pinned = personas.load_or_create(tmp_path, "windows", timezone="Asia/Tokyo", locale="ja-JP")
    assert (pinned.seed, pinned.platform_version) == (first.seed, first.platform_version)
    assert (pinned.timezone, pinned.locale) == ("Asia/Tokyo", "ja-JP")
    # None leaves the saved value, "" clears it.
    kept = personas.load_or_create(tmp_path, "windows", timezone=None)
    assert kept.timezone == "Asia/Tokyo"
    cleared = personas.load_or_create(tmp_path, "windows", timezone="", locale="")
    assert (cleared.timezone, cleared.locale) == (None, None)
    assert cleared.seed == first.seed


def test_corrupt_file_is_regenerated(tmp_path):
    personas.persona_path(tmp_path).write_text("{not json", encoding="utf-8")
    p = personas.load_or_create(tmp_path, "linux")
    assert json.loads(personas.persona_path(tmp_path).read_text(encoding="utf-8"))["seed"] == p.seed


def test_invalid_saved_values_are_regenerated(tmp_path):
    personas.persona_path(tmp_path).write_text(
        json.dumps({"seed": -1, "platform": "windows"}), "utf-8"
    )
    assert personas.load(tmp_path) is None
    assert personas.load_or_create(tmp_path, "windows").seed > 0


@pytest.mark.parametrize(
    ("host", "platform", "level"),
    [
        ("windows", "windows", personas.OK),
        ("windows", "macos", personas.WARN),
        ("windows", "linux", personas.UNSUPPORTED),
        ("linux", "windows", personas.WARN),
        ("macos", "macos", personas.OK),
        ("macos", "windows", personas.WARN),
        ("macos", "linux", personas.UNSUPPORTED),
    ],
)
def test_compatibility(host, platform, level):
    assert personas.compatibility(host, platform)[0] == level
