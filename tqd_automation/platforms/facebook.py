"""Publish a text (+ images) post on a personal Facebook profile in one call.

The Post button is pressed at most once per call. A pending ledger line is written before that
click, so an unconfirmed result counts as sent and the guards block any retry of the same text.
"""

from __future__ import annotations

import json
import time
from functools import partial
from typing import Any, Literal

from src.mcp_server.server import FoxProfileError

from .. import data_dir
from ..guards import GuardBusy, Guards
from ..humanize import pause
from ..judge import PageState, make_judge
from ..result import PostResult

PLATFORM = "facebook"
HOME = "https://www.facebook.com/"
TIMELINE = "https://www.facebook.com/me"
DIALOG_GONE_SECONDS = 30
TIMELINE_TIMEOUT_MS = 60_000

# Found on the live page (vi-VN UI) with English names as fallback. The composer opens as an
# unnamed dialog at /post/create; its file input stays hidden but accepts files directly.
LOCATORS = {
    "composer_open": "role=button[name=/bạn đang nghĩ gì|on your mind/i]",
    "dialog": "[role=dialog] form",
    "textbox": "[role=dialog] [role=textbox]",
    "photo_button": "[role=dialog] >> role=button[name=/Thêm ảnh hoặc video|Photo\\/video/i]",
    "file_input": "[role=dialog] input[type=file][multiple]",
    "media_preview": "[role=dialog] img[src^='blob:']",
    "audience_button": "[role=dialog] >> role=button[name=/Đối tượng của bài viết|Post audience/i]",
    "audience_only_me": "role=radio[name=/^(Chỉ mình tôi|Only me)$/i]",
    "audience_done": "role=button[name=/Đã lựa chọn xong đối tượng|^Done$/i]",
    "post_button": "[role=dialog] >> role=button[name=/^(Đăng|Post)$/]",
    "close_button": "role=button[name=/^(Đóng|Close)$/] >> visible=true",
    "discard_button": "[role=dialog] >> role=button[name=/^(Rời khỏi|Leave)$/] >> visible=true",
}

DIALOG_OPEN = "!!document.querySelector('[role=dialog] form')"
HAS_FILE_INPUT = "!!document.querySelector('[role=dialog] input[type=file][multiple]')"
# Permalink of the timeline post containing the text. Timeline posts are [aria-posinset] blocks
# ([role=article] is mostly comments). Their timestamp links carry a placeholder href that
# Facebook swaps for the real /posts/pfbid... link on focus; the photo link is the fallback.
# Only tracking parameters (`__cft__`, `__tn__`, ...) are dropped.
FIND_POST_URL = """(async () => {
  const text = %s;
  const hit = [...document.querySelectorAll('[aria-posinset], [role=article]')]
    .find(el => el.innerText.includes(text));
  if (!hit) return '';
  const post = hit.closest('[aria-posinset]') || hit;
  const clean = href => {
    const url = new URL(href, location.origin);
    for (const key of [...url.searchParams.keys()]) if (key.startsWith('__')) url.searchParams.delete(key);
    return url.toString();
  };
  for (const a of post.querySelectorAll('a[href^="?"], a[href*="__cft__"]')) {
    a.focus();
    a.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
  }
  await new Promise(resolve => setTimeout(resolve, 500));
  const links = [...post.querySelectorAll('a[href]')].map(a => a.href);
  const permalink = links.find(h => /\\/posts\\/|story_fbid|pfbid/.test(h));
  if (permalink) return clean(permalink);
  const photo = links.find(h => /\\/photo\\/?\\?fbid=/.test(h));
  return photo ? clean(photo) : '';
})()"""

HARD_STOPS = (PageState.CHECKPOINT.value, PageState.CAPTCHA.value)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def post(
    profile: str,
    text: str,
    images: list[str] | None = None,
    audience: Literal["default", "only_me"] = "default",
    dry_run: bool = False,
    browser: Any = None,
    judge: Any = None,
    guards: Guards | None = None,
) -> PostResult:
    if browser is None:
        from ..client import Browser

        browser = Browser(profile)
    judge = judge or make_judge()
    guards = guards or Guards()
    try:
        with guards.run_lock(PLATFORM, profile):
            run = _Run(profile, text, images or [], browser, judge, guards)
            try:
                return run.go(audience, dry_run)
            except FoxProfileError as e:  # a page step failed: report it, never retry the click
                return run._end("failed", post_clicked=run.clicked, detail=str(e)[:300])
    except GuardBusy as e:
        return PostResult("blocked", detail=str(e))


class _Run:
    def __init__(self, profile, text, images, browser, judge, guards):
        self.profile, self.text, self.images = profile, text, images
        self.b, self.judge, self.guards = browser, judge, guards
        self.clicked = False
        self.record = partial(
            guards.record,
            attempt_id=guards.new_attempt(),
            platform=PLATFORM,
            profile=profile,
            text=text,
        )

    def go(self, audience: str, dry_run: bool) -> PostResult:
        reason = self.guards.check(PLATFORM, self.profile, self.text)
        if reason:
            return self._end("blocked", detail=reason)
        verdict = self.judge.content_ok(PLATFORM, self.text)
        if verdict.label == "block":
            return self._end("blocked", detail=f"content blocked: {verdict.detail}")
        if self.guards.require_approval():
            return self._draft(audience)

        self.b.ensure_running()
        self.b.navigate(HOME)
        pause()
        stop = self._stop_unless(PageState.READY.value, PageState.COMPOSER_OPEN.value)
        if stop:
            return stop

        self.b.click(LOCATORS["composer_open"])
        self.b.wait_for(LOCATORS["dialog"])
        pause()
        stop = self._stop_unless(PageState.COMPOSER_OPEN.value, PageState.READY.value)
        if stop:
            return stop

        if self.images:
            if not self.b.evaluate(HAS_FILE_INPUT)["result"]:
                self.b.click(LOCATORS["photo_button"])
            self.b.upload(LOCATORS["file_input"], self.images)
            self.b.wait_for(LOCATORS["media_preview"])
            pause()
        self.b.click(LOCATORS["textbox"])
        self.b.keyboard_type(self.text)
        pause()
        if audience == "only_me":
            for key in ("audience_button", "audience_only_me", "audience_done"):
                self.b.click(LOCATORS[key])
                pause()

        if dry_run:
            evidence = self._evidence()
            self.b.click(LOCATORS["close_button"])
            self.b.click(LOCATORS["discard_button"])
            return self._end("dry_run", evidence=evidence, detail="stopped before Post")

        return self._publish()

    def _publish(self) -> PostResult:
        self.record(status="pending", post_clicked=True)
        self.clicked = True
        self.b.click(LOCATORS["post_button"])
        sent = partial(self._end, post_clicked=True)

        for _ in range(DIALOG_GONE_SECONDS):
            _sleep(1)
            if not self.b.evaluate(DIALOG_OPEN)["result"]:
                break
        else:
            return sent("failed", evidence=self._evidence(), detail="publish unconfirmed")

        self.b.navigate(TIMELINE)
        first_line = self.text.strip().splitlines()[0][:40]
        try:
            self.b.wait_for_text(first_line, timeout=TIMELINE_TIMEOUT_MS)
        except FoxProfileError:
            return sent(
                "failed",
                evidence=self._evidence(),
                detail="publish unconfirmed: post not visible on timeline",
            )
        url = self.b.evaluate(FIND_POST_URL % json.dumps(first_line))["result"] or ""
        state, _ = self._look()
        if state.label in HARD_STOPS:
            self.guards.lockout(PLATFORM, self.profile, f"{state.label} after publishing")
            return sent("blocked", evidence=self._evidence(), detail=f"{state.label} after publish")
        detail = "" if url else "post visible but its link was not found"
        return sent("published", url=url, evidence=self._evidence(), detail=detail)

    def _look(self):
        url = self.b.evaluate("location.href")["result"]
        snapshot = self.b.snapshot()["snapshot"]
        return self.judge.page_state(PLATFORM, url, snapshot), url

    def _stop_unless(self, *allowed: str) -> PostResult | None:
        state, url = self._look()
        if state.label in HARD_STOPS:
            self.guards.lockout(PLATFORM, self.profile, f"{state.label} page at {url}")
            return self._end("blocked", evidence=self._evidence(), detail=f"{state.label} page")
        if state.label == PageState.LOGGED_OUT.value:
            return self._end("failed", detail="logged out: log in manually in the profile")
        if state.label not in allowed:
            snapshot = self.b.snapshot(interactive_only=True)["snapshot"]
            return self._end(
                "needs_agent", detail=f"unexpected page state {state.label}", snapshot=snapshot
            )
        return None

    def _evidence(self) -> str:
        return self.guards.save_evidence(self.b.screenshot_png(), PLATFORM, self.profile)

    def _draft(self, audience: str) -> PostResult:
        folder = data_dir() / "drafts"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{PLATFORM}-{time.strftime('%Y%m%d-%H%M%S')}.json"
        draft = {"profile": self.profile, "text": self.text, "images": self.images}
        path.write_text(json.dumps({**draft, "audience": audience}, ensure_ascii=False), "utf-8")
        return self._end("awaiting_approval", detail=f"draft saved to {path.as_posix()}")

    def _end(
        self,
        status: str,
        *,
        post_clicked: bool = False,
        url: str = "",
        evidence: str = "",
        detail: str = "",
        snapshot: str = "",
    ) -> PostResult:
        self.record(
            status=status, post_clicked=post_clicked, url=url, evidence=evidence, detail=detail
        )
        return PostResult(status, url=url, evidence=evidence, detail=detail, snapshot=snapshot)
