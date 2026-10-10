"""Blocking safety gates that stand in for human approval, plus the post ledger and evidence files.

The ledger is append-only. Macros record a `pending` line with `post_clicked=True` before pressing
Post, then a second line with the outcome under the same `attempt_id`. An attempt counts as a sent
post when any of its lines was clicked or published, so a crash or an unconfirmed result can never
be retried into a double post.

A macro holds `run_lock` from `check` until its outcome is recorded, so two runs for the same
account cannot both pass the checks before either has written its pending line.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import data_dir

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DEFAULT_DAILY_CAPS = {"facebook": 3, "tiktok": 2}
DEFAULT_MIN_INTERVAL_MIN = 90
DUPLICATE_WINDOW = timedelta(days=30)
# A run lock older than this was left by a crashed run; no posting run takes this long.
STALE_LOCK_SECONDS = 30 * 60


class GuardBusy(Exception):
    """Another posting run holds the lock for this platform and profile."""


def text_hash(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class Guards:
    def __init__(self, now: Callable[[], datetime] | None = None):
        self._now = now or (lambda: datetime.now(TZ))
        self.dir = data_dir()

    @contextmanager
    def run_lock(self, platform: str, profile: str) -> Iterator[None]:
        path = self.dir / f"run_{platform}_{profile}.lock"
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            if time.time() - path.stat().st_mtime > STALE_LOCK_SECONDS:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise GuardBusy(f"another {platform} post for {profile} is in progress") from None
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            yield
        finally:
            path.unlink(missing_ok=True)

    @staticmethod
    def new_attempt() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def require_approval() -> bool:
        return os.getenv("TQD_REQUIRE_APPROVAL", "false").lower() == "true"

    def check(self, platform: str, profile: str, text: str) -> str | None:
        """Return why a post must not be sent now, or None when it may go."""
        if os.getenv("TQD_AUTOMATION_DISABLED") == "1" or (self.dir / "KILL").exists():
            return "kill switch on"
        if self._lockout_file(platform, profile).exists():
            return (
                "locked out after checkpoint; delete the lockout file after resolving it manually"
            )

        now = self._now().astimezone(TZ)
        sent = self._sent_posts(platform)
        mine = [p for p in sent if p["profile"] == profile]

        cap = int(
            os.getenv(f"TQD_{platform.upper()}_DAILY_CAP", DEFAULT_DAILY_CAPS.get(platform, 1))
        )
        if sum(p["ts"].date() == now.date() for p in mine) >= cap:
            return "daily cap reached"

        interval = timedelta(
            minutes=int(os.getenv("TQD_MIN_INTERVAL_MIN", DEFAULT_MIN_INTERVAL_MIN))
        )
        if any(now - p["ts"] < interval for p in mine):
            return "too soon"

        digest = text_hash(text)
        if any(p["text_sha256"] == digest and now - p["ts"] < DUPLICATE_WINDOW for p in sent):
            return "duplicate text"
        return None

    def lockout(self, platform: str, profile: str, reason: str) -> None:
        path = self._lockout_file(platform, profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{self._now().isoformat(timespec='seconds')} {reason}\n", encoding="utf-8")

    def record(
        self,
        *,
        attempt_id: str,
        platform: str,
        profile: str,
        status: str,
        post_clicked: bool = False,
        text: str = "",
        url: str = "",
        evidence: str = "",
        detail: str = "",
    ) -> None:
        line = {
            "ts": self._now().isoformat(timespec="seconds"),
            "attempt_id": attempt_id,
            "platform": platform,
            "profile": profile,
            "status": status,
            "post_clicked": post_clicked,
            "text_sha256": text_hash(text),
            "url": url,
            "evidence": evidence,
            "detail": detail,
        }
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / "post_ledger.jsonl"
        # A crash mid-write leaves no final newline; without one this line would be glued onto the
        # broken one and skipped by the reader.
        prefix = "" if _ends_with_newline(path) else "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(prefix + json.dumps(line, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def save_evidence(self, png: bytes, platform: str, profile: str) -> str:
        now = self._now().astimezone(TZ)
        path = self.dir / "evidence" / f"{now:%Y-%m-%d}" / f"{platform}-{profile}-{now:%H%M%S}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        return path.as_posix()

    def _lockout_file(self, platform: str, profile: str) -> Path:
        return self.dir / f"lockout_{platform}_{profile}"

    def _sent_posts(self, platform: str) -> list[dict]:
        """One entry per sent attempt on `platform`, timed by its first line."""
        path = self.dir / "post_ledger.jsonl"
        if not path.is_file():
            return []
        attempts: dict[str, dict] = {}
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                line = json.loads(raw)
            except ValueError:
                continue  # a line cut short by a crash; it was written before any click
            if line.get("platform") != platform:
                continue
            attempt = attempts.setdefault(
                line.get("attempt_id") or raw,
                {
                    "ts": datetime.fromisoformat(line["ts"]).astimezone(TZ),
                    "profile": line.get("profile"),
                    "text_sha256": line.get("text_sha256"),
                    "sent": False,
                },
            )
            if line.get("post_clicked") or line.get("status") == "published":
                attempt["sent"] = True
        return [a for a in attempts.values() if a["sent"]]


def _ends_with_newline(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            f.seek(-1, os.SEEK_END)
            return f.read(1) == b"\n"
    except FileNotFoundError:
        return True
    except OSError:  # empty file: seeking before the start
        return True
