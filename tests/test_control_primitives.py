import pytest

from src.services.browser.control import ControlError, PageController
from tests.test_control import FakeContext, FakePage, run

ARIA = """\
- heading "Feed" [level=1]
- button "Create post"
- text: Welcome back
- textbox "What's on your mind?"
- link "Home":
  - /url: /
- img "Avatar"
"""


class _First:
    def __init__(self, page, selector):
        self._page = page
        self._selector = selector

    async def set_input_files(self, paths, timeout=None):
        self._page.uploads.append((self._selector, list(paths)))

    async def wait_for(self, timeout=None):
        self._page.waited_text.append(self._selector)


class _Locator:
    def __init__(self, page, selector):
        self.first = _First(page, selector)
        self._page = page

    async def aria_snapshot(self):
        return ARIA


class _Mouse:
    def __init__(self, page):
        self._page = page

    async def wheel(self, dx, dy):
        self._page.wheels.append((dx, dy))


class PrimitivePage(FakePage):
    def __init__(self, url="about:blank"):
        super().__init__(url)
        self.uploads = []
        self.waited_text = []
        self.waited_urls = []
        self.wheels = []
        self.scripts = []
        self.mouse = _Mouse(self)

    def locator(self, selector):
        return _Locator(self, selector)

    def get_by_text(self, text):
        return _Locator(self, text)

    async def wait_for_url(self, pattern, timeout=None):
        self.waited_urls.append(pattern)

    async def evaluate(self, script):
        self.scripts.append(script)


class PrimitiveContext(FakeContext):
    def __init__(self):
        self.pages = [PrimitivePage("https://p0.test/")]


@pytest.fixture
def outbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    box = tmp_path / "media_outbox"
    box.mkdir()
    return box


def test_upload_passes_resolved_paths(outbox):
    image = outbox / "a.png"
    image.write_bytes(b"png")
    ctx = PrimitiveContext()
    result = run(
        PageController(ctx).dispatch(
            "upload", {"selector": "input", "paths": ["media_outbox/a.png"]}
        )
    )
    assert result["uploaded"] == 1
    assert ctx.pages[0].uploads == [("input", [str(image.resolve())])]


def test_upload_refuses_files_outside_the_upload_dir(outbox, tmp_path):
    secret = tmp_path / "cookies.png"
    secret.write_bytes(b"x")
    with pytest.raises(ControlError, match="outside"):
        run(
            PageController(PrimitiveContext()).dispatch(
                "upload", {"selector": "i", "paths": [str(secret)]}
            )
        )


def test_upload_refuses_traversal(outbox, tmp_path):
    (tmp_path / "x.png").write_bytes(b"x")
    with pytest.raises(ControlError, match="outside"):
        run(
            PageController(PrimitiveContext()).dispatch(
                "upload", {"selector": "i", "paths": ["media_outbox/../x.png"]}
            )
        )


def test_upload_refuses_missing_files(outbox):
    with pytest.raises(ControlError, match="not found"):
        run(
            PageController(PrimitiveContext()).dispatch(
                "upload", {"selector": "i", "paths": ["media_outbox/no.png"]}
            )
        )


def test_upload_refuses_other_file_types(outbox):
    (outbox / "run.exe").write_bytes(b"MZ")
    with pytest.raises(ControlError, match="type"):
        run(
            PageController(PrimitiveContext()).dispatch(
                "upload", {"selector": "i", "paths": ["media_outbox/run.exe"]}
            )
        )


def test_upload_needs_at_least_one_file(outbox):
    with pytest.raises(ControlError, match="at least one"):
        run(PageController(PrimitiveContext()).dispatch("upload", {"selector": "i", "paths": []}))


def test_waits_forward_to_the_page():
    ctx = PrimitiveContext()
    c = PageController(ctx)
    run(c.dispatch("wait_for_url", {"pattern": "/me"}))
    run(c.dispatch("wait_for_text", {"text": "Posted"}))
    assert ctx.pages[0].waited_urls == ["**/me**"]
    assert ctx.pages[0].waited_text == ["Posted"]


def test_scroll_by_wheel_and_to_edges():
    ctx = PrimitiveContext()
    c = PageController(ctx)
    run(c.dispatch("scroll", {"dy": 600}))
    run(c.dispatch("scroll", {"to": "top"}))
    run(c.dispatch("scroll", {"to": "bottom"}))
    page = ctx.pages[0]
    assert page.wheels == [(0, 600)]
    assert page.scripts == [
        "window.scrollTo(0, 0)",
        "window.scrollTo(0, document.body.scrollHeight)",
    ]


def test_scroll_rejects_unknown_edge():
    with pytest.raises(ControlError, match="top"):
        run(PageController(PrimitiveContext()).dispatch("scroll", {"to": "middle"}))


def test_interactive_snapshot_keeps_only_controls():
    result = run(
        PageController(PrimitiveContext()).dispatch("snapshot", {"interactive_only": True})
    )
    lines = result["snapshot"].splitlines()
    assert lines == [
        '- button "Create post"',
        '- textbox "What\'s on your mind?"',
        '- link "Home":',
    ]


def test_full_snapshot_is_unchanged():
    result = run(PageController(PrimitiveContext()).dispatch("snapshot", {}))
    assert result["snapshot"] == ARIA
