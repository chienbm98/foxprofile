"""Publish a post with up to four images (or one video) on X in one call.

Same safety structure as the other macros (see `common.py`). X has no per-post "only me" audience,
so every live post is public.
"""

from __future__ import annotations

import json
import time
from pathlib import PurePath
from typing import Any

from .. import rules
from ..guards import Guards
from ..humanize import pause
from ..judge import PageState
from ..result import PostResult
from .common import BaseRun, first_line, run_macro

PLATFORM = "x"
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov"}
MAX_PHOTOS = 4
PUBLISH_SECONDS = 30
FIND_ATTEMPTS = 6

# Found on the live page (vi-VN UI); X's data-testid hooks do not depend on the language.
LOCATORS = {
    "composer_url": "https://x.com/compose/post",
    "textbox": "[role=dialog] [data-testid=tweetTextarea_0]",
    "file_input": "[role=dialog] [data-testid=fileInput]",
    "media_preview": "[role=dialog] [data-testid=attachments]",
    "post_button": "[role=dialog] [data-testid=tweetButton]",
    "close_button": "[role=dialog] [data-testid=app-bar-close]",
    "discard_button": "[role=alertdialog] [data-testid=confirmationSheetCancel]",
    "profile_link": "[data-testid=AppTabBar_Profile_Link]",
}

COMPOSER_OPEN = "!!document.querySelector('[role=dialog] [data-testid=tweetTextarea_0]')"
COMPOSER_TEXT = (
    "(document.querySelector('[role=dialog] [data-testid=tweetTextarea_0]') || {}).innerText || ''"
)
ALERT_TEXT = (
    "[...document.querySelectorAll('[role=alert], [data-testid=toast]')].map(e => e.innerText.trim())"
    ".filter(Boolean).join(' | ').slice(0, 200)"
)
# The "Your post was sent · View" toast links to the new post.
TOAST_URL = "(document.querySelector('[role=alert] a[href*=\"/status/\"]') || {}).href || ''"
PROFILE_HREF = "document.querySelector('[data-testid=AppTabBar_Profile_Link]').getAttribute('href')"
# The status link of the newest post on the profile whose text contains the given start.
FIND_POST_URL = """(() => {
  const text = %s;
  const post = [...document.querySelectorAll('article[data-testid=tweet]')]
    .find(a => a.innerText.includes(text));
  const link = post && post.querySelector('a[href*="/status/"]:has(time)');
  return link ? link.href : '';
})()"""


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def post(
    profile: str,
    text: str,
    media: list[str] | None = None,
    dry_run: bool = False,
    browser: Any = None,
    judge: Any = None,
    guards: Guards | None = None,
) -> PostResult:
    return run_macro(_Run, profile, text, media, "default", dry_run, browser, judge, guards)


class _Run(BaseRun):
    platform = PLATFORM

    def validate(self) -> str | None:
        suffixes = [PurePath(m).suffix.lower() for m in self.media]
        if all(s in PHOTO_EXT for s in suffixes):
            return (
                None
                if len(suffixes) <= MAX_PHOTOS
                else f"X takes at most {MAX_PHOTOS} photos as media"
            )
        if len(suffixes) == 1 and suffixes[0] in VIDEO_EXT:
            return None
        return "X media must be up to 4 photos (jpg/png/webp/gif) or exactly one video (mp4/mov)"

    def act(self, visibility: str, dry_run: bool) -> PostResult:
        self.b.navigate(LOCATORS["composer_url"])
        pause()
        stop = self._stop_unless(PageState.COMPOSER_OPEN.value, PageState.READY.value)
        if stop:
            return stop

        if self.media:
            self.b.upload(LOCATORS["file_input"], self.media)
            self.b.wait_for(LOCATORS["media_preview"])
            pause()
        self.b.click(LOCATORS["textbox"])
        self.b.keyboard_type(self.text)
        pause()
        if first_line(self.text) not in self.b.evaluate(COMPOSER_TEXT)["result"]:
            snapshot = self.b.snapshot(interactive_only=True)["snapshot"]
            return self._end("needs_agent", detail="text was not entered", snapshot=snapshot)

        if dry_run:
            evidence = self._evidence()
            self.b.click(LOCATORS["close_button"])
            self.b.click(LOCATORS["discard_button"])  # delete, not save as draft
            return self._end("dry_run", evidence=evidence, detail="stopped before Post")

        self.click_post(LOCATORS["post_button"])
        for _ in range(PUBLISH_SECONDS):
            _sleep(1)
            if not self.b.evaluate(COMPOSER_OPEN)["result"]:
                break
            alert = self.b.evaluate(ALERT_TEXT)["result"]
            # "Your post was sent" can show while the composer is still closing.
            if any(p in alert.lower() for p in rules.PLATFORMS[PLATFORM]["published"]):
                break
            if alert:
                return self.sent(
                    "failed", evidence=self._evidence(), detail=f"publish unconfirmed: {alert}"
                )
        else:
            return self.sent("failed", evidence=self._evidence(), detail="publish unconfirmed")

        url = self.b.evaluate(TOAST_URL)["result"] or ""
        if not url:
            # Right after posting X may serve a cached profile timeline: load it afresh each try.
            profile_url = "https://x.com" + self.b.evaluate(PROFILE_HREF)["result"]
            find = FIND_POST_URL % json.dumps(first_line(self.text))
            for _ in range(FIND_ATTEMPTS):
                self.b.navigate(profile_url)
                _sleep(5)
                url = self.b.evaluate(find)["result"] or ""
                if url:
                    break
        return self.confirm_safe(url)
