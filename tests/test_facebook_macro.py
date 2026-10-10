"""The Facebook macro publishes once, stops on checkpoints, and never re-clicks Post."""

import json
from datetime import datetime, timedelta

import pytest

from tqd_automation.guards import TZ, Guards
from tqd_automation.judge import CompositeJudge, HeuristicJudge
from tqd_automation.platforms import facebook
from tqd_automation.platforms.facebook import LOCATORS as L
from tqd_automation.platforms.facebook import post

HOME = "https://www.facebook.com/"
FEED = '- button "Dũng ơi, bạn đang nghĩ gì thế?"\n- button "Ảnh/video"'
COMPOSER = (
    '- dialog:\n  - main:\n    - text: Tạo bài viết\n    - form "Bài viết":\n      - textbox "x"'
)
LOGIN = '- textbox "Email hoặc số điện thoại"\n- textbox "Mật khẩu"\n- button "Đăng nhập"'
POST_URL = "https://www.facebook.com/someone/posts/pfbid0abc"
NOW = datetime(2026, 10, 10, 9, 0, tzinfo=TZ)

REQUIRED = {
    "composer_open",
    "dialog",
    "textbox",
    "photo_button",
    "file_input",
    "media_preview",
    "audience_button",
    "audience_only_me",
    "audience_done",
    "post_button",
    "close_button",
    "discard_button",
}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("TQD_AUTOMATION_DIR", str(tmp_path / "automation_data"))
    for key in ("TQD_AUTOMATION_DISABLED", "TQD_REQUIRE_APPROVAL", "TQD_MIN_INTERVAL_MIN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(facebook, "pause", lambda *a: None)
    monkeypatch.setattr(facebook, "_sleep", lambda s: None)


class FakeBrowser:
    """Scripted page: `pages` maps the step to the snapshot shown there."""

    def __init__(self, home=FEED, composer=COMPOSER, dialog_closes=True, on_timeline=True):
        self.url, self.page = "about:blank", ""
        self.home, self.composer = home, composer
        self.dialog_closes, self.on_timeline = dialog_closes, on_timeline
        self.calls = []
        self.dialog_open = False

    def _log(self, *call):
        self.calls.append(call)

    def ensure_running(self):
        self._log("ensure_running")

    def navigate(self, url):
        self._log("navigate", url)
        self.url = url
        self.page = self.home if url == HOME else '- link "Trang cá nhân"'
        return {"url": url}

    def snapshot(self, interactive_only=False):
        self._log("snapshot", interactive_only)
        return {"snapshot": self.page}

    def click(self, selector, timeout=10_000):
        self._log("click", selector)
        if selector == L["composer_open"]:
            self.dialog_open, self.page = True, self.composer
        if selector == L["post_button"] and self.dialog_closes:
            self.dialog_open = False
        return {}

    def keyboard_type(self, text):
        self._log("type", text)

    def press(self, key):
        self._log("press", key)

    def upload(self, selector, paths):
        self._log("upload", selector, paths)

    def wait_for(self, selector, timeout=15_000):
        self._log("wait_for", selector)

    def wait_for_text(self, text, timeout=15_000):
        self._log("wait_for_text", text)
        if not self.on_timeline:
            raise facebook.FoxProfileError("FoxProfile API 422: TimeoutError")

    def screenshot_png(self):
        self._log("screenshot")
        return b"\x89PNG"

    def evaluate(self, script):
        self._log("evaluate", script[:20])
        if script == "location.href":
            return {"result": self.url}
        if "[role=dialog]" in script and "querySelector" in script and "article" not in script:
            return {"result": self.dialog_open}
        return {"result": POST_URL}

    def clicks(self, key):
        return sum(1 for c in self.calls if c == ("click", L[key]))


def run(browser, text="Chào buổi sáng", images=("media_outbox/a.png",), **kw):
    guards = kw.pop("guards", Guards(now=lambda: NOW))
    return post(
        "fb",
        text,
        list(images),
        browser=browser,
        judge=CompositeJudge(HeuristicJudge()),
        guards=guards,
        **kw,
    )


def ledger(tmp_path):
    path = tmp_path / "automation_data" / "post_ledger.jsonl"
    return [json.loads(x) for x in path.read_text("utf-8").splitlines()] if path.exists() else []


def test_locators_are_complete():
    assert set(L) >= REQUIRED and all(L[k] for k in REQUIRED)


def test_guard_block_makes_no_browser_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("TQD_AUTOMATION_DISABLED", "1")
    b = FakeBrowser()
    result = run(b)
    assert (result.status, result.detail) == ("blocked", "kill switch on")
    assert b.calls == []
    assert ledger(tmp_path)[0]["status"] == "blocked"


def test_held_run_lock_blocks_without_ledger_line(tmp_path):
    g = Guards(now=lambda: NOW)
    b = FakeBrowser()
    with g.run_lock("facebook", "fb"):
        result = run(b, guards=g)
    assert result.status == "blocked" and "in progress" in result.detail
    assert b.calls == [] and ledger(tmp_path) == []


def test_blocked_content_makes_no_browser_calls():
    b = FakeBrowser()
    assert run(b, text="x" * 5001).status == "blocked"
    assert b.calls == []


def test_approval_mode_writes_a_draft(monkeypatch, tmp_path):
    monkeypatch.setenv("TQD_REQUIRE_APPROVAL", "true")
    b = FakeBrowser()
    assert run(b).status == "awaiting_approval"
    assert b.calls == []
    drafts = list((tmp_path / "automation_data" / "drafts").glob("facebook-*.json"))
    assert json.loads(drafts[0].read_text("utf-8"))["text"] == "Chào buổi sáng"


def test_checkpoint_locks_out_and_blocks(tmp_path):
    b = FakeBrowser()
    b.navigate = lambda url: setattr(b, "url", "https://www.facebook.com/checkpoint/1")
    result = run(b)
    assert result.status == "blocked"
    assert result.evidence.endswith(".png")
    assert (tmp_path / "automation_data" / "lockout_facebook_fb").exists()
    assert b.clicks("post_button") == 0


def test_logged_out_fails():
    result = run(FakeBrowser(home=LOGIN))
    assert result.status == "failed" and "log in" in result.detail


def test_unknown_page_needs_agent():
    result = run(FakeBrowser(home="- heading 'Something new'"))
    assert result.status == "needs_agent"
    assert result.snapshot


def test_composer_not_recognised_needs_agent():
    b = FakeBrowser(composer="- heading 'Odd'")
    assert run(b).status == "needs_agent"
    assert b.clicks("post_button") == 0


def test_dry_run_never_clicks_post(tmp_path):
    b = FakeBrowser()
    result = run(b, audience="only_me", dry_run=True)
    assert result.status == "dry_run" and result.evidence
    assert b.clicks("post_button") == 0
    assert b.clicks("audience_only_me") == 1
    assert b.clicks("discard_button") == 1
    assert all(not line["post_clicked"] for line in ledger(tmp_path))


def test_happy_path_publishes_once(tmp_path):
    b = FakeBrowser()
    result = run(b)
    assert result.status == "published" and result.url == POST_URL and result.evidence
    names = [c[0] for c in b.calls]
    assert names.index("upload") < names.index("type")
    assert b.clicks("post_button") == 1
    lines = ledger(tmp_path)
    assert [(x["status"], x["post_clicked"]) for x in lines] == [
        ("pending", True),
        ("published", True),
    ]
    assert lines[0]["attempt_id"] == lines[1]["attempt_id"]
    assert lines[0]["text_sha256"]


def test_write_ahead_line_exists_before_the_click(tmp_path):
    b = FakeBrowser()
    seen = []
    original = b.click

    def click(selector, timeout=10_000):
        if selector == L["post_button"]:
            seen.append([x["status"] for x in ledger(tmp_path)])
        return original(selector, timeout)

    b.click = click
    run(b)
    assert seen == [["pending"]]


def test_text_only_post_skips_upload():
    b = FakeBrowser()
    assert run(b, images=()).status == "published"
    assert not any(c[0] == "upload" for c in b.calls)


def test_dialog_still_open_is_unconfirmed(tmp_path):
    b = FakeBrowser(dialog_closes=False)
    result = run(b)
    assert result.status == "failed" and "publish unconfirmed" in result.detail
    assert b.clicks("post_button") == 1
    assert ledger(tmp_path)[-1]["post_clicked"] is True


def test_post_missing_from_timeline_is_unconfirmed_and_not_retried(tmp_path, monkeypatch):
    b = FakeBrowser(on_timeline=False)
    result = run(b)
    assert result.status == "failed" and "not visible on timeline" in result.detail
    assert b.clicks("post_button") == 1
    assert ledger(tmp_path)[-1]["post_clicked"] is True

    monkeypatch.setenv("TQD_MIN_INTERVAL_MIN", "0")
    again = FakeBrowser()
    later = Guards(now=lambda: NOW + timedelta(minutes=1))
    assert run(again, guards=later).detail == "duplicate text"
    assert again.calls == []


def test_page_error_before_post_is_a_plain_failure(tmp_path):
    b = FakeBrowser()

    def broken(selector, timeout=10_000):
        raise facebook.FoxProfileError("FoxProfile API 422: TimeoutError: Locator.click")

    b.click = broken
    result = run(b)
    assert result.status == "failed" and "TimeoutError" in result.detail
    assert ledger(tmp_path)[-1]["post_clicked"] is False


def test_page_error_after_post_click_counts_as_sent(tmp_path):
    b = FakeBrowser()

    def broken(script):
        raise facebook.FoxProfileError("FoxProfile API 502: browser closed")

    original = b.click

    def click(selector, timeout=10_000):
        original(selector, timeout)
        if selector == L["post_button"]:
            b.evaluate = broken

    b.click = click
    result = run(b)
    assert result.status == "failed"
    assert [x["post_clicked"] for x in ledger(tmp_path)] == [True, True]
