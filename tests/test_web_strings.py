import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
INDEX = SRC / "web" / "index.html"
PLACEHOLDER = re.compile(r"{(\w+)}")
KEY = re.compile(r"[A-Za-z_]\w*")


def _dictionary(source: str, language: str) -> dict[str, str]:
    marker = re.search(rf"^  {re.escape(language)}:\s*\{{", source, re.MULTILINE)
    assert marker, f"Missing web language dictionary: {language}"
    start = source.index("{", marker.start()) + 1
    result: dict[str, str] = {}
    pos = start

    while pos < len(source):
        while pos < len(source) and (source[pos].isspace() or source[pos] == ","):
            pos += 1
        if source[pos] == "}":
            return result

        match = KEY.match(source, pos)
        assert match, f"Expected a translation key at character {pos}"
        key = match.group()
        pos = match.end()
        while source[pos].isspace():
            pos += 1
        assert source[pos] == ":", f"Expected ':' after {key}"
        pos += 1
        while source[pos].isspace():
            pos += 1
        quote = source[pos]
        assert quote in ("'", '"'), f"Expected a string value for {key}"
        pos += 1
        value_start = pos
        escaped = False
        while pos < len(source):
            char = source[pos]
            if char == quote and not escaped:
                break
            escaped = char == "\\" and not escaped
            pos += 1
        assert pos < len(source), f"Unterminated translation string for {key}"
        result[key] = source[value_start:pos]
        pos += 1

    raise AssertionError(f"Unterminated web language dictionary: {language}")


def test_web_languages_have_same_keys_and_placeholders():
    source = INDEX.read_text(encoding="utf-8")
    tables = {code: _dictionary(source, code) for code in ("en", "vi", "zh")}
    expected_keys = set(tables["en"])
    assert all(set(table) == expected_keys for table in tables.values())

    for key, english in tables["en"].items():
        placeholders = set(PLACEHOLDER.findall(english))
        assert all(
            set(PLACEHOLDER.findall(table[key])) == placeholders for table in tables.values()
        ), key


def test_web_language_switch_covers_each_dictionary():
    source = INDEX.read_text(encoding="utf-8")
    switch = source.split('role="group" aria-label="Language"', maxsplit=1)[1].split("</div>", 1)[0]
    buttons = set(re.findall(r'data-lang="([a-z-]+)"', switch))
    assert buttons == {"en", "vi", "zh"}
    assert '"Accept-Language": lang' in source
    assert ".seg { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));" in source
