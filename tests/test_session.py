import asyncio
import json

from src.services.browser import runner, session


def test_save_and_load_round_trip(tmp_path):
    urls = ["https://a.test/", "http://b.test/x?y=1"]
    assert session.save(str(tmp_path), urls) is True
    assert session.load(str(tmp_path)) == urls


def test_only_http_urls_are_kept(tmp_path):
    session.save(
        str(tmp_path),
        ["about:blank", "https://a.test/", "file:///etc/passwd", "javascript:alert(1)", "data:,x"],
    )
    assert session.load(str(tmp_path)) == ["https://a.test/"]


def test_empty_list_keeps_previous_snapshot(tmp_path):
    session.save(str(tmp_path), ["https://a.test/"])
    assert session.save(str(tmp_path), ["about:blank"]) is False
    assert session.load(str(tmp_path)) == ["https://a.test/"]


def test_tab_count_is_capped(tmp_path):
    session.save(str(tmp_path), [f"https://t{i}.test/" for i in range(100)])
    assert len(session.load(str(tmp_path))) == session.MAX_TABS


def test_missing_or_corrupt_file_loads_nothing(tmp_path):
    assert session.load(str(tmp_path)) == []
    session.tabs_path(str(tmp_path)).write_text("{broken", encoding="utf-8")
    assert session.load(str(tmp_path)) == []
    session.tabs_path(str(tmp_path)).write_text(json.dumps({"tabs": "nope"}), encoding="utf-8")
    assert session.load(str(tmp_path)) == []


def test_tampered_file_cannot_restore_local_urls(tmp_path):
    session.tabs_path(str(tmp_path)).write_text(
        json.dumps({"tabs": ["file:///C:/Windows/win.ini", "https://ok.test/"]}),
        encoding="utf-8",
    )
    assert session.load(str(tmp_path)) == ["https://ok.test/"]


class FakePage:
    def __init__(self, url="about:blank"):
        self.url = url
        self.closed = False

    def is_closed(self):
        return self.closed

    async def goto(self, url, **_):
        if "fail" in url:
            raise RuntimeError("net::ERR")
        self.url = url

    async def bring_to_front(self):
        pass


class FakeContext:
    def __init__(self):
        self.pages = [FakePage()]

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page


def test_restore_reuses_blank_tab_and_opens_the_rest():
    ctx = FakeContext()
    n = asyncio.run(runner.restore_tabs(ctx, ["https://a.test/", "https://b.test/"]))
    assert n == 2
    assert [p.url for p in ctx.pages] == ["https://a.test/", "https://b.test/"]


def test_restore_survives_a_failing_tab():
    ctx = FakeContext()
    asyncio.run(runner.restore_tabs(ctx, ["https://fail.test/", "https://ok.test/"]))
    assert [p.url for p in ctx.pages] == ["about:blank", "https://ok.test/"]


def test_snapshot_saves_changes_and_keeps_tabs_when_window_closes(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "TAB_SNAPSHOT_SECONDS", 0.01)
    ctx = FakeContext()
    ctx.pages[0].url = "https://a.test/"

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(runner.snapshot_tabs(ctx, str(tmp_path), stop))
        await asyncio.sleep(0.05)
        ctx.pages.append(FakePage("https://b.test/"))
        await asyncio.sleep(0.05)
        for page in ctx.pages:  # user closes every tab: the browser window goes away
            page.closed = True
        stop.set()
        await task

    asyncio.run(scenario())
    assert session.load(str(tmp_path)) == ["https://a.test/", "https://b.test/"]
