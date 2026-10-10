"""Guards replace human approval: each rule blocks a post on its own, and pressed-but-unconfirmed
posts count as sent so a retry can never double-post."""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tqd_automation import REPO_ROOT, data_dir
from tqd_automation.guards import STALE_LOCK_SECONDS, TZ, GuardBusy, Guards

NOW = datetime(2026, 10, 10, 20, 0, tzinfo=TZ)


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TQD_AUTOMATION_DIR", str(tmp_path / "automation_data"))
    for key in (
        "TQD_AUTOMATION_DISABLED",
        "TQD_REQUIRE_APPROVAL",
        "TQD_FACEBOOK_DAILY_CAP",
        "TQD_TIKTOK_DAILY_CAP",
        "TQD_MIN_INTERVAL_MIN",
    ):
        monkeypatch.delenv(key, raising=False)


def guards(at=NOW):
    return Guards(now=lambda: at)


def sent(g, text="bài đăng", status="published", post_clicked=False, profile="fb"):
    g.record(
        attempt_id=g.new_attempt(),
        platform="facebook",
        profile=profile,
        status=status,
        post_clicked=post_clicked,
        text=text,
    )


def test_clean_state_allows_post():
    assert guards().check("facebook", "fb", "Xin chào") is None


def test_kill_switch_env(monkeypatch):
    monkeypatch.setenv("TQD_AUTOMATION_DISABLED", "1")
    assert guards().check("facebook", "fb", "Xin chào") == "kill switch on"


def test_kill_switch_file(tmp_path):
    (tmp_path / "automation_data").mkdir()
    (tmp_path / "automation_data" / "KILL").write_text("")
    assert guards().check("facebook", "fb", "Xin chào") == "kill switch on"


def test_lockout_blocks_only_that_platform_and_profile(tmp_path):
    g = guards()
    g.lockout("facebook", "fb", "checkpoint page")
    assert "locked out" in g.check("facebook", "fb", "Xin chào")
    assert g.check("tiktok", "fb", "Xin chào") is None
    assert "checkpoint page" in (tmp_path / "automation_data" / "lockout_facebook_fb").read_text(
        encoding="utf-8"
    )


def test_daily_cap(monkeypatch):
    for i in range(3):
        sent(guards(NOW - timedelta(hours=3 * (i + 1))), text=f"bài {i}")
    assert guards().check("facebook", "fb", "bài mới") == "daily cap reached"
    monkeypatch.setenv("TQD_FACEBOOK_DAILY_CAP", "4")
    assert guards().check("facebook", "fb", "bài mới") is None


def test_daily_cap_resets_at_local_midnight():
    for i in range(3):
        sent(guards(datetime(2026, 10, 9, 20 + i, 0, tzinfo=TZ)), text=f"bài {i}")
    assert guards(datetime(2026, 10, 10, 0, 30, tzinfo=TZ)).check("facebook", "fb", "mới") is None


def test_daily_cap_is_per_profile():
    for i in range(3):
        sent(guards(NOW - timedelta(hours=3 * (i + 1))), text=f"bài {i}", profile="other")
    assert guards().check("facebook", "fb", "bài mới") is None


def test_min_interval(monkeypatch):
    sent(guards(NOW - timedelta(minutes=30)))
    assert guards().check("facebook", "fb", "bài khác") == "too soon"
    monkeypatch.setenv("TQD_MIN_INTERVAL_MIN", "20")
    assert guards().check("facebook", "fb", "bài khác") is None


def test_duplicate_text_is_normalized():
    sent(guards(NOW - timedelta(days=5)), text="Chào   buổi sáng\n")
    assert guards().check("facebook", "fb", "chào buổi SÁNG") == "duplicate text"
    assert guards().check("tiktok", "fb", "chào buổi SÁNG") is None


def test_duplicate_window_is_30_days():
    sent(guards(NOW - timedelta(days=31)), text="Chào buổi sáng")
    assert guards().check("facebook", "fb", "Chào buổi sáng") is None


def test_failed_attempt_without_click_does_not_count():
    sent(guards(NOW - timedelta(minutes=5)), status="failed")
    assert guards().check("facebook", "fb", "bài đăng") is None


def test_failed_attempt_after_click_counts_for_every_rule(monkeypatch):
    sent(guards(NOW - timedelta(minutes=5)), status="failed", post_clicked=True)
    assert guards().check("facebook", "fb", "bài khác") == "too soon"
    monkeypatch.setenv("TQD_MIN_INTERVAL_MIN", "0")
    assert guards().check("facebook", "fb", "bài đăng") == "duplicate text"
    monkeypatch.setenv("TQD_FACEBOOK_DAILY_CAP", "1")
    assert guards().check("facebook", "fb", "bài khác") == "daily cap reached"


def test_lone_write_ahead_line_counts_as_sent():
    # The process died between pressing Post and confirming the result.
    sent(guards(NOW - timedelta(minutes=5)), status="pending", post_clicked=True)
    assert guards().check("facebook", "fb", "bài khác") == "too soon"


def test_write_ahead_and_outcome_count_once(monkeypatch):
    monkeypatch.setenv("TQD_MIN_INTERVAL_MIN", "0")
    monkeypatch.setenv("TQD_FACEBOOK_DAILY_CAP", "2")
    g = guards(NOW - timedelta(hours=1))
    attempt = g.new_attempt()
    for status in ("pending", "published"):
        g.record(
            attempt_id=attempt,
            platform="facebook",
            profile="fb",
            status=status,
            post_clicked=True,
            text="bài một",
        )
    assert guards().check("facebook", "fb", "bài hai") is None


def test_require_approval(monkeypatch):
    assert Guards.require_approval() is False
    monkeypatch.setenv("TQD_REQUIRE_APPROVAL", "TRUE")
    assert Guards.require_approval() is True


def test_record_writes_hash_not_text(tmp_path):
    g = guards()
    g.record(
        attempt_id="a1",
        platform="facebook",
        profile="fb",
        status="published",
        post_clicked=True,
        text="Nội dung riêng tư",
        url="https://www.facebook.com/1/posts/2",
        evidence="automation_data/evidence/x.png",
    )
    line = json.loads((tmp_path / "automation_data" / "post_ledger.jsonl").read_text("utf-8"))
    assert line["attempt_id"] == "a1"
    assert line["status"] == "published"
    assert line["url"].endswith("/posts/2")
    assert len(line["text_sha256"]) == 64
    assert "Nội dung" not in json.dumps(line, ensure_ascii=False)
    assert line["ts"].startswith("2026-10-10T20:00:00")


def test_new_attempt_ids_are_unique():
    g = guards()
    assert g.new_attempt() != g.new_attempt()


def test_save_evidence(tmp_path):
    path = guards().save_evidence(b"\x89PNG", "facebook", "fb")
    assert path.endswith("automation_data/evidence/2026-10-10/facebook-fb-200000.png")
    assert Path(path).read_bytes() == b"\x89PNG"


def test_line_after_a_crash_cut_line_still_counts(tmp_path):
    ledger = tmp_path / "automation_data" / "post_ledger.jsonl"
    ledger.parent.mkdir()
    ledger.write_text('{"ts": "2026-10-10T19:00:00+07:00", "attempt_id": "x", "plat', "utf-8")
    sent(guards(NOW - timedelta(minutes=5)), status="pending", post_clicked=True)
    assert guards().check("facebook", "fb", "bài khác") == "too soon"


def test_run_lock_blocks_a_second_run_and_is_released():
    g = guards()
    with g.run_lock("facebook", "fb"):
        with pytest.raises(GuardBusy), g.run_lock("facebook", "fb"):
            pass
        with g.run_lock("tiktok", "fb"):
            pass
    with g.run_lock("facebook", "fb"):
        pass


def test_stale_run_lock_is_taken_over(tmp_path):
    lock = tmp_path / "automation_data" / "run_facebook_fb.lock"
    lock.parent.mkdir()
    lock.write_text("1234")
    old = time.time() - STALE_LOCK_SECONDS - 60
    os.utime(lock, (old, old))
    with guards().run_lock("facebook", "fb"):
        pass
    assert not lock.exists()


def test_data_dir_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("TQD_AUTOMATION_DIR")
    monkeypatch.chdir(tmp_path)
    assert data_dir() == REPO_ROOT / "automation_data"
    assert (REPO_ROOT / "tqd_automation").is_dir()
