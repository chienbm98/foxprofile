import pathlib
import re

from src.core.strings import STRINGS, current_language, get_string, set_language

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


def test_languages_have_same_keys():
    assert set(STRINGS["vi"]) == set(STRINGS["en"]) == set(STRINGS["zh"])


def test_placeholders_match_between_languages():
    field = re.compile(r"{(\w+)}")
    for key, en in STRINGS["en"].items():
        expected = set(field.findall(en))
        assert expected == set(field.findall(STRINGS["vi"][key])), key
        assert expected == set(field.findall(STRINGS["zh"][key])), key


def test_every_used_key_exists():
    used = set()
    for path in SRC.rglob("*.py"):
        used |= set(re.findall(r'get_string\(\s*"(\w+)"', path.read_text(encoding="utf-8")))
    missing = used - set(STRINGS["en"])
    assert not missing, f"get_string keys missing from STRINGS: {sorted(missing)}"


def test_simplified_chinese_can_be_selected():
    previous = current_language()
    try:
        set_language("zh")
        assert current_language() == "zh"
        assert get_string("app_subtitle") == "反检测浏览器配置管理器"
    finally:
        set_language(previous)
