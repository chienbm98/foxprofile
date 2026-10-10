import asyncio

import pytest

from src.services.browser.control import ControlError, PageController, _check_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("example.com", "https://example.com"),
        ("http://a.vn/x", "http://a.vn/x"),
        ("about:blank", "about:blank"),
        ("localhost:8080/x", "https://localhost:8080/x"),
    ],
)
def test_allowed_urls(url, expected):
    assert _check_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/win.ini",
        "view-source:https://a.com",
        "javascript:alert(1)",
        "chrome://x",
        "about:config",
        "about:logins",
        "data:text/html,<script>alert(1)</script>",
    ],
)
def test_blocked_urls(url):
    with pytest.raises(ControlError):
        _check_url(url)


class FakePage:
    def __init__(self, url="about:blank"):
        self.url = url
        self.closed = False

    def is_closed(self):
        return self.closed

    async def title(self):
        return "T"

    async def goto(self, url, wait_until="load"):
        self.url = url

    async def close(self):
        self.closed = True

    async def bring_to_front(self):
        pass


class FakeContext:
    def __init__(self, n=1):
        self.pages = [FakePage(f"https://p{i}.test/") for i in range(n)]

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page


def run(coro):
    return asyncio.run(coro)


def test_dispatch_rejects_unknown_action_and_bad_params():
    c = PageController(FakeContext())
    with pytest.raises(ControlError, match="Unknown action"):
        run(c.dispatch("rm_rf", {}))
    with pytest.raises(ControlError, match="Invalid parameters"):
        run(c.dispatch("navigate", {"nope": 1}))


def test_navigate_uses_active_tab():
    ctx = FakeContext(2)
    c = PageController(ctx)
    result = run(c.dispatch("navigate", {"url": "example.com"}))
    assert result == {"url": "https://example.com", "title": "T"}
    assert ctx.pages[-1].url == "https://example.com"


def test_tabs_select_and_close():
    ctx = FakeContext(2)
    c = PageController(ctx)
    tabs = run(c.dispatch("tab_select", {"index": 0}))["tabs"]
    assert [t["active"] for t in tabs] == [True, False]
    tabs = run(c.dispatch("tab_close", {"index": 0}))["tabs"]
    assert [t["url"] for t in tabs] == ["https://p1.test/"]
    with pytest.raises(ControlError, match="last tab"):
        run(c.dispatch("tab_close", {"index": 0}))
    with pytest.raises(ControlError, match="No tab"):
        run(c.dispatch("tab_select", {"index": 5}))


# ---------------------------------------------------------------------------
# Percent-encoded scheme bypass (fix 3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "%66ile:///C:/Windows/win.ini",  # decodes to file:///...
        "java%73cript:alert(1)",  # decodes to javascript:...
        "%76iew-source:https://a.com",  # decodes to view-source:...
    ],
)
def test_percent_encoded_blocked_schemes(url):
    """Percent-encoded disallowed schemes must be caught before scheme detection."""
    with pytest.raises(ControlError):
        _check_url(url)


@pytest.mark.parametrize("url", ["[", "[]", "[::1", "http://[::1"])
def test_malformed_url_is_a_control_error(url):
    with pytest.raises(ControlError):
        _check_url(url)
