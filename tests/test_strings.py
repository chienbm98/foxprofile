import ast
import pathlib
import re
from html.parser import HTMLParser

import pytest

from src.core import strings
from src.core.strings import STRINGS

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
INDEX = SRC / "web" / "index.html"
FIELD = re.compile(r"{(\w+)}")
LANGS = sorted(STRINGS)


def test_languages_are_the_supported_set():
    assert LANGS == ["en", "zh-CN"]


def test_languages_have_same_keys():
    for lang in LANGS:
        assert set(STRINGS[lang]) == set(STRINGS["en"]), lang


def test_placeholders_match_between_languages():
    for lang in LANGS:
        for key, en in STRINGS["en"].items():
            assert set(FIELD.findall(en)) == set(FIELD.findall(STRINGS[lang][key])), (lang, key)


def test_every_used_key_exists():
    used = set()
    for path in SRC.rglob("*.py"):
        used |= set(re.findall(r'get_string\(\s*"(\w+)"', path.read_text(encoding="utf-8")))
    missing = used - set(STRINGS["en"])
    assert not missing, f"get_string keys missing from STRINGS: {sorted(missing)}"


# --- language choice -------------------------------------------------------------------


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(strings, "_PREFS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(strings, "_lang", None)
    monkeypatch.setattr(strings, "LANGUAGE", "")
    monkeypatch.setattr(strings, "_system_language", lambda: None)
    return strings


def test_language_defaults_to_en(fresh):
    assert fresh.current_language() == "en"


def test_language_follows_a_chinese_system(fresh, monkeypatch):
    monkeypatch.setattr(fresh, "_system_language", lambda: "zh-CN")
    assert fresh.current_language() == "zh-CN"


def test_saved_choice_beats_system_and_env_beats_saved(fresh, monkeypatch):
    monkeypatch.setattr(fresh, "_system_language", lambda: "zh-CN")
    fresh.set_language("zh-CN", persist=True)
    monkeypatch.setattr(fresh, "_system_language", lambda: None)
    monkeypatch.setattr(fresh, "_lang", None)
    assert fresh.current_language() == "zh-CN"
    monkeypatch.setattr(fresh, "_lang", None)
    monkeypatch.setattr(fresh, "LANGUAGE", "zh_CN")
    assert fresh.current_language() == "zh-CN"
    monkeypatch.setattr(fresh, "_lang", None)
    monkeypatch.setattr(fresh, "LANGUAGE", "en")
    assert fresh.current_language() == "en"


def test_legacy_vi_setting_falls_back_to_system_language(fresh, monkeypatch):
    fresh._PREFS_FILE.write_text('{"language": "vi"}', encoding="utf-8")
    monkeypatch.setattr(fresh, "_system_language", lambda: None)
    assert fresh.current_language() == "en"
    monkeypatch.setattr(fresh, "_lang", None)
    monkeypatch.setattr(fresh, "_system_language", lambda: "zh-CN")
    assert fresh.current_language() == "zh-CN"


def test_unknown_language_is_ignored(fresh):
    fresh.set_language("xx", persist=True)
    assert fresh.current_language() == "en"
    assert not fresh._PREFS_FILE.exists()


# --- web panel I18N --------------------------------------------------------------------


def _web_i18n() -> dict[str, dict[str, str]]:
    text = INDEX.read_text(encoding="utf-8")
    block = text[text.index("const I18N = {") : text.index("const store")]
    out: dict[str, dict[str, str]] = {}
    for body in re.split(r"^  (?=(?:\"[\w-]+\"|\w+): \{$)", block, flags=re.M)[1:]:
        lang = body.split(":")[0].strip('"')
        out[lang] = dict(re.findall(r'(\w+):\s*("(?:[^"\\]|\\.)*")', body))
    return out


def test_web_languages_match_desktop():
    assert sorted(_web_i18n()) == LANGS


def test_web_languages_have_same_keys_and_placeholders():
    web = _web_i18n()
    for lang in LANGS:
        assert set(web[lang]) == set(web["en"]), lang
        for key, en in web["en"].items():
            assert set(FIELD.findall(en)) == set(FIELD.findall(web[lang][key])), (lang, key)


def test_web_used_keys_exist():
    text = INDEX.read_text(encoding="utf-8")
    used = set(re.findall(r'data-(?:t|title)="(\w+)"', text))
    used |= set(re.findall(r"\bt\(\s*\"(\w+)\"", text))
    used = {k for k in used if not k.endswith("_")}  # dynamic: t("fp_mode_" + mode)
    assert used - set(_web_i18n()["en"]) == set()


def test_web_language_buttons():
    text = INDEX.read_text(encoding="utf-8")
    assert re.findall(r'data-lang="([\w-]+)"', text) == ["zh-CN", "en"]


# --- no hard-coded English ---------------------------------------------------------------

# Brand names and technical values that are the same in every language.
ALLOWED = {
    "FoxProfile",
    "MCP",
    "Chrome",
    "Camoufox",
    "Camoufox (Firefox)",
    "Firefox",
    "English",
    "OS",
    "GPU",
    "CPU",
    "API",
    "JSON",
    "WebGL",
    "WebRTC",
    "Cookie",
    "Proxy",
    "Profile",
    "Fingerprint",
    "Consolas",
    "Enter",
    "Tab",
    "Esc",
    "Backspace",
}
WORDS = re.compile(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}")
CAP_WORD = re.compile(r"[A-Z][a-z]{2,}")


def _looks_english(text: str) -> bool:
    """Two or more words in a row, or one capitalised word, and not a known technical value."""
    text = text.strip()
    if text in ALLOWED or text.startswith(("#", "http", "/", "{")):
        return False
    return bool(WORDS.search(text) or CAP_WORD.fullmatch(text))


# Call names whose first argument is shown to the user, and keywords that always are.
TEXT_CALLS = {"Text", "Option", "Tab", "SnackBar", "Button", "TextButton", "OutlinedButton"}
TEXT_KWARGS = {"text", "label", "hint_text", "helper_text", "tooltip", "title", "error_text"}


def _literals(node: ast.AST):
    """String literals that flow straight into the displayed text (not through get_string)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node
    elif isinstance(node, ast.JoinedStr):
        for part in node.values:
            yield from _literals(part)
    elif isinstance(node, ast.BinOp):
        yield from _literals(node.left)
        yield from _literals(node.right)
    elif isinstance(node, ast.IfExp):
        yield from _literals(node.body)
        yield from _literals(node.orelse)
    elif isinstance(node, (ast.List, ast.Tuple)):
        for el in node.elts:
            yield from _literals(el)


def _call_name(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def hardcoded_ui_strings() -> list[str]:
    found = []
    for path in sorted((SRC / "ui").rglob("*.py")):
        for call in (
            n
            for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(n, ast.Call)
        ):
            shown = [kw.value for kw in call.keywords if kw.arg in TEXT_KWARGS]
            if _call_name(call) in TEXT_CALLS and call.args:
                shown.append(call.args[0])
            for expr in shown:
                for lit in _literals(expr):
                    if _looks_english(lit.value):
                        found.append(f"{path.relative_to(SRC.parent)}:{lit.lineno} {lit.value!r}")
    return found


def test_desktop_ui_has_no_hardcoded_english():
    assert hardcoded_ui_strings() == []


class _StaticText(HTMLParser):
    """Visible text and title/placeholder/aria-label attributes outside <script>/<style>/<svg>
    that are not driven by data-t / data-title."""

    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, bool]] = []
        self.found: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for name in ("title", "placeholder", "aria-label"):
            if (
                a.get(name)
                and "data-title" not in a
                and "data-t" not in a
                and _looks_english(a[name])
            ):
                self.found.append(f"<{tag} {name}={a[name]!r}>")
        if tag not in ("meta", "link", "br", "input", "img", "use", "path"):
            self.stack.append((tag, "data-t" in a))

    def handle_endtag(self, tag):
        while self.stack and self.stack.pop()[0] != tag:
            pass

    def handle_data(self, data):
        if any(t in ("script", "style", "svg", "title") or driven for t, driven in self.stack):
            return
        if _looks_english(data):
            self.found.append(data.strip())


def test_web_static_html_has_no_hardcoded_english():
    text = INDEX.read_text(encoding="utf-8")
    parser = _StaticText()
    parser.feed(text)
    assert parser.found == []


# JS: h("tag", {props}, "literal child"), toast("..."), and displayed props with literal values.
JS_SHOWN = [
    re.compile(r'\bh\(\s*"[\w-]+"\s*,\s*\{[^{}]*\}\s*,\s*"((?:[^"\\\n]|\\.)*)"'),
    re.compile(r'\btoast\(\s*"((?:[^"\\\n]|\\.)*)"'),
    re.compile(r'\b(?:placeholder|title|aria-label|textContent)\s*[:=]\s*"((?:[^"\\\n]|\\.)*)"'),
]


def test_web_script_has_no_hardcoded_english():
    text = INDEX.read_text(encoding="utf-8")
    script = text[text.index("const store") :]
    found = [m for rx in JS_SHOWN for m in rx.findall(script) if _looks_english(m)]
    assert found == []
