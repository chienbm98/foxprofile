import pathlib
import re

from src.core.strings import STRINGS

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


def test_languages_have_same_keys():
    assert set(STRINGS["vi"]) == set(STRINGS["en"])


def test_placeholders_match_between_languages():
    field = re.compile(r"{(\w+)}")
    for key, en in STRINGS["en"].items():
        assert set(field.findall(en)) == set(field.findall(STRINGS["vi"][key])), key


def test_every_used_key_exists():
    used = set()
    for path in SRC.rglob("*.py"):
        used |= set(re.findall(r'get_string\(\s*"(\w+)"', path.read_text(encoding="utf-8")))
    missing = used - set(STRINGS["en"])
    assert not missing, f"get_string keys missing from STRINGS: {sorted(missing)}"
