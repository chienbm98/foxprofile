"""Publish a text (+ images) post on a personal Facebook profile in one call.

The Post button is pressed at most once per call. A pending ledger line is written before that
click, so an unconfirmed result counts as sent and the guards block any retry of the same text.
"""

from __future__ import annotations

import json
import time
from typing import Any, Literal

from src.mcp_server.server import FoxProfileError

from ..guards import Guards
from ..humanize import pause
from ..judge import PageState
from ..result import PostResult
from .common import BaseRun, first_line, run_macro

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
    return run_macro(_Run, profile, text, images, audience, dry_run, browser, judge, guards)


class _Run(BaseRun):
    platform = PLATFORM

    def act(self, audience: str, dry_run: bool) -> PostResult:
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

        if self.media:
            if not self.b.evaluate(HAS_FILE_INPUT)["result"]:
                self.b.click(LOCATORS["photo_button"])
            self.b.upload(LOCATORS["file_input"], self.media)
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

        self.click_post(LOCATORS["post_button"])
        for _ in range(DIALOG_GONE_SECONDS):
            _sleep(1)
            if not self.b.evaluate(DIALOG_OPEN)["result"]:
                break
        else:
            return self.sent("failed", evidence=self._evidence(), detail="publish unconfirmed")

        self.b.navigate(TIMELINE)
        line = first_line(self.text)
        try:
            self.b.wait_for_text(line, timeout=TIMELINE_TIMEOUT_MS)
        except FoxProfileError:
            return self.sent(
                "failed",
                evidence=self._evidence(),
                detail="publish unconfirmed: post not visible on timeline",
            )
        return self.confirm_safe(self.b.evaluate(FIND_POST_URL % json.dumps(line))["result"] or "")
