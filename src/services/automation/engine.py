"""Profile groups, scheduled tasks and the activity log.

A task is a list of steps run in each target profile's browser: launch (or reuse
a running one), run the steps, stop. Targets are profile names and/or a group.
Tasks repeat every N minutes or daily at HH:MM, with random jitter so a fleet of
profiles does not act in lockstep.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import pathlib
import random
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from ...core.config import ACTIVITY_LOG, AUTOMATION_FILE, LAUNCH_WAIT_TIMEOUT
from ...core.logging import get_logger

if TYPE_CHECKING:
    from ...interfaces import IBrowserLauncher, IProfileManager

logger = get_logger("automation")

# Seconds between automatic sign-in attempts for one profile.
LOGIN_COOLDOWN = int(os.getenv("FOXPROFILE_LOGIN_COOLDOWN", "600"))
MAX_PARALLEL = int(os.getenv("FOXPROFILE_AUTOMATION_PARALLEL", "3"))
TICK_SECONDS = 20
SCREENSHOT_DIR = os.getenv("FOXPROFILE_SCREENSHOT_DIR", "screenshots")

# verb -> required keys
STEP_VERBS: dict[str, tuple[str, ...]] = {
    "goto": ("url",),
    "wait": (),
    "scroll": (),
    "click": ("selector",),
    "type": ("selector", "text"),
    "press": ("key",),
    "wait_for": ("selector",),
    "evaluate": ("script",),
    "screenshot": (),
    "text": (),
    "session_check": (),
}

WARMUP_SITES = [
    "https://www.google.com/",
    "https://en.wikipedia.org/wiki/Special:Random",
    "https://www.youtube.com/",
    "https://news.ycombinator.com/",
    "https://www.reddit.com/",
]

TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "session-check-gmail": [{"do": "session_check"}],
    "keepalive-gmail": [
        {"do": "goto", "url": "https://mail.google.com/"},
        {"do": "wait", "seconds": [6, 12]},
        {"do": "scroll"},
        {"do": "wait", "seconds": [3, 8]},
        {"do": "goto", "url": "https://myaccount.google.com/"},
        {"do": "wait", "seconds": [4, 9]},
        {"do": "screenshot"},
    ],
    "browse-warmup": [
        s
        for site in WARMUP_SITES
        for s in (
            {"do": "goto", "url": site},
            {"do": "wait", "seconds": [4, 10]},
            {"do": "scroll"},
            {"do": "wait", "seconds": [2, 6]},
        )
    ],
}


class AutomationError(Exception):
    pass


def validate_steps(steps: Any) -> list[dict[str, Any]]:
    if not isinstance(steps, list) or not steps:
        raise AutomationError("steps must be a non-empty list")
    if len(steps) > 200:
        raise AutomationError("at most 200 steps per task")
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or step.get("do") not in STEP_VERBS:
            raise AutomationError(f"step {i}: 'do' must be one of {', '.join(sorted(STEP_VERBS))}")
        missing = [k for k in STEP_VERBS[step["do"]] if k not in step]
        if missing:
            raise AutomationError(f"step {i} ({step['do']}) needs: {', '.join(missing)}")
        seconds = step.get("seconds")
        if step["do"] == "wait" and seconds is not None:
            ok = isinstance(seconds, (int, float)) or (
                isinstance(seconds, list)
                and len(seconds) == 2
                and all(isinstance(x, (int, float)) for x in seconds)
            )
            if not ok or (isinstance(seconds, (int, float)) and seconds > 3600):
                raise AutomationError(f"step {i}: seconds must be a number or [min, max]")
    return steps


class ActivityLog:
    def __init__(self, path: str | None = None) -> None:
        self.path = pathlib.Path(path or ACTIVITY_LOG)
        self._lock = threading.Lock()

    def add(self, event: str, profile: str | None = None, **fields: Any) -> None:
        row = {"t": round(time.time(), 1), "event": event, "profile": profile, **fields}
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def tail(self, limit: int = 100, profile: str | None = None) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows = []
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if profile is None or row.get("profile") == profile:
                rows.append(row)
                if len(rows) >= limit:
                    break
        return rows


def _next_run(task: dict[str, Any], now: float) -> float | None:
    jitter = random.uniform(0, max(0, task.get("jitter_seconds", 0)))
    if task.get("every_minutes"):
        return now + task["every_minutes"] * 60 + jitter
    if task.get("daily_at"):
        hh, mm = map(int, task["daily_at"].split(":"))
        base = datetime.fromtimestamp(now).replace(hour=hh, minute=mm, second=0, microsecond=0)
        if base.timestamp() <= now:
            base += timedelta(days=1)
        return base.timestamp() + jitter
    return None


class Automation:
    def __init__(
        self,
        pm: IProfileManager,
        launcher: IBrowserLauncher,
        sync: Any = None,
        vault: Any = None,
        path: str | None = None,
        log: ActivityLog | None = None,
    ) -> None:
        self.pm = pm
        self.launcher = launcher
        self.sync = sync
        self.vault = vault
        self._last_login: dict[str, float] = {}
        self._busy_login: set[str] = set()
        self.path = pathlib.Path(path or AUTOMATION_FILE)
        self.log = log or ActivityLog()
        self._lock = threading.RLock()
        self._running: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pool = ThreadPoolExecutor(max_workers=MAX_PARALLEL)

    # -- storage --
    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("groups", {})
        data.setdefault("tasks", {})
        return data

    def _save(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    # -- groups --
    def groups(self) -> dict[str, list[str]]:
        with self._lock:
            return self._load()["groups"]

    def set_group(self, name: str, profiles: list[str]) -> list[str]:
        if not re.fullmatch(r"[\w.\- ]{1,60}", name):
            raise AutomationError("group name: 1-60 letters, digits, space, . _ -")
        unknown = [p for p in profiles if p not in self.pm.profiles]
        if unknown:
            raise AutomationError(f"unknown profiles: {', '.join(unknown)}")
        with self._lock:
            data = self._load()
            data["groups"][name] = sorted(set(profiles))
            self._save(data)
            return data["groups"][name]

    def delete_group(self, name: str) -> bool:
        with self._lock:
            data = self._load()
            if data["groups"].pop(name, None) is None:
                return False
            self._save(data)
            return True

    # -- tasks --
    def tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._load()["tasks"].values())

    def create_task(
        self,
        name: str,
        steps: list[dict[str, Any]] | None = None,
        template: str | None = None,
        profiles: list[str] | None = None,
        group: str | None = None,
        every_minutes: int | None = None,
        daily_at: str | None = None,
        jitter_seconds: int = 0,
        stop_after: bool = True,
        sync: bool = False,
        enabled: bool = True,
    ) -> dict[str, Any]:
        if template:
            if template not in TEMPLATES:
                raise AutomationError(f"unknown template; use one of {', '.join(TEMPLATES)}")
            steps = [dict(s) for s in TEMPLATES[template]]
        steps = validate_steps(steps)
        if not profiles and not group:
            raise AutomationError("give profiles and/or a group")
        if every_minutes is not None and every_minutes < 1:
            raise AutomationError("every_minutes must be >= 1")
        if every_minutes and daily_at:
            raise AutomationError("use every_minutes or daily_at, not both")
        if daily_at and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", daily_at):
            raise AutomationError("daily_at must be HH:MM")
        task = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "steps": steps,
            "profiles": profiles or [],
            "group": group,
            "every_minutes": every_minutes,
            "daily_at": daily_at,
            "jitter_seconds": max(0, jitter_seconds),
            "stop_after": stop_after,
            "sync": sync,
            "enabled": enabled,
            "last_run": None,
            "last_status": None,
            "next_run": None,
        }
        task["next_run"] = _next_run(task, time.time()) if enabled else None
        with self._lock:
            data = self._load()
            data["tasks"][task["id"]] = task
            self._save(data)
        return task

    def set_enabled(self, task_id: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            data = self._load()
            task = data["tasks"].get(task_id)
            if task is None:
                raise AutomationError(f"task {task_id} not found")
            task["enabled"] = enabled
            task["next_run"] = _next_run(task, time.time()) if enabled else None
            self._save(data)
            return task

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            data = self._load()
            if data["tasks"].pop(task_id, None) is None:
                return False
            self._save(data)
            return True

    def targets(self, task: dict[str, Any]) -> list[str]:
        names = list(task.get("profiles") or [])
        if task.get("group"):
            names += self.groups().get(task["group"], [])
        seen: dict[str, None] = {}
        for n in names:
            if n in self.pm.profiles:
                seen[n] = None
        return list(seen)

    # -- execution --
    def run_task(self, task_id: str, wait: bool = False) -> dict[str, Any]:
        with self._lock:
            task = self._load()["tasks"].get(task_id)
            if task is None:
                raise AutomationError(f"task {task_id} not found")
            if task_id in self._running:
                raise AutomationError("task is already running")
            self._running.add(task_id)
        future = self._pool.submit(self._run_task, task)
        if wait:
            return future.result()
        return {"started": task_id, "profiles": self.targets(task)}

    def _run_task(self, task: dict[str, Any]) -> dict[str, Any]:
        results: dict[str, str] = {}
        status = "error"
        try:
            self.log.add("task_start", task=task["id"], name=task["name"])
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as ex:
                futures = {n: ex.submit(self._run_profile, task, n) for n in self.targets(task)}
                for n, f in futures.items():
                    try:
                        results[n] = f.result()
                    except Exception as e:
                        results[n] = f"error: {e}"
            failed = [n for n, r in results.items() if r != "ok"]
            status = "ok" if not failed else f"{len(failed)} failed"
            self.log.add("task_end", task=task["id"], status=status, results=results)
        finally:
            with self._lock:
                self._running.discard(task["id"])
                data = self._load()
                live = data["tasks"].get(task["id"])
                if live:
                    live["last_run"] = time.time()
                    live["last_status"] = status
                    live["next_run"] = _next_run(live, time.time()) if live["enabled"] else None
                    self._save(data)
        return results

    def _run_profile(self, task: dict[str, Any], name: str) -> str:
        profile = self.pm.profiles.get(name)
        if profile is None:
            return "error: profile gone"
        launched_here = False
        try:
            if task.get("sync") and self.sync and self.sync.configured:
                with contextlib.suppress(Exception):
                    self.sync.pull(name)
            if not self.launcher.is_running(name):
                if not self.launcher.start_thread(profile, lambda m: None):
                    return "error: could not start"
                launched_here = True
                ok, error = self.launcher.wait_for_launch(name, LAUNCH_WAIT_TIMEOUT)
                if not ok:
                    return f"error: launch failed: {error}"
            if getattr(profile, "auto_login", False):
                self._check_running(name)
            self.run_steps(name, task["steps"], task["id"])
            return "ok"
        except Exception as e:
            self.log.add("step_error", name, task=task["id"], error=str(e)[:300])
            return f"error: {str(e)[:200]}"
        finally:
            if launched_here and task.get("stop_after", True):
                self.launcher.stop_profile(name)
                if task.get("sync") and self.sync and self.sync.configured:
                    time.sleep(2)
                    try:
                        self.sync.push(name)
                    except Exception as e:
                        self.log.add("sync_error", name, error=str(e)[:300])

    def run_steps(self, name: str, steps: list[dict[str, Any]], task_id: str = "") -> list[Any]:
        out: list[Any] = []
        for step in validate_steps(steps):
            verb = step["do"]
            self.log.add("step", name, task=task_id, step=verb)
            c = self.launcher.control
            if verb == "goto":
                out.append(c(name, "navigate", {"url": step["url"]}))
            elif verb == "wait":
                s = step.get("seconds", 3)
                time.sleep(random.uniform(*s) if isinstance(s, list) else s)
            elif verb == "scroll":
                dist = step.get("pixels") or random.randint(400, 1400)
                c(
                    name,
                    "evaluate",
                    {"script": f"window.scrollBy({{top:{int(dist)},behavior:'smooth'}})"},
                )
            elif verb == "click":
                out.append(c(name, "click", {"selector": step["selector"]}))
            elif verb == "type":
                params = {k: step[k] for k in ("selector", "text", "submit", "clear") if k in step}
                out.append(c(name, "type", params))
            elif verb == "press":
                out.append(c(name, "press", {k: step[k] for k in ("key", "selector") if k in step}))
            elif verb == "wait_for":
                out.append(c(name, "wait_for", {"selector": step["selector"]}))
            elif verb == "evaluate":
                out.append(c(name, "evaluate", {"script": step["script"]}))
            elif verb == "text":
                out.append(c(name, "text", {"selector": step.get("selector", "body")}))
            elif verb == "session_check":
                out.append(self._check_running(name))
            elif verb == "screenshot":
                shot = c(name, "screenshot", {"full_page": bool(step.get("full_page"))})
                folder = pathlib.Path(SCREENSHOT_DIR) / name
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{int(time.time())}.png"
                path.write_bytes(base64.b64decode(shot["png_base64"]))
                out.append({"saved": str(path)})
        return out

    # -- session check --
    def _check_running(self, name: str) -> dict[str, Any]:
        from ..browser import session_check

        result = session_check.check(self.launcher.control, name)
        fields: dict[str, Any] = {
            "session_state": result["state"],
            "session_checked_at": time.time(),
        }
        if result["email"]:
            fields["email"] = result["email"]
        self.pm.update_meta(name, **fields)
        self.log.add("session_check", name, state=result["state"], email=result["email"])
        profile = self.pm.profiles.get(name)
        if (
            result["state"] == "logged_out"
            and profile is not None
            and getattr(profile, "auto_login", False)
        ):
            relogin = self._relogin_running(name, manual=False)
            if relogin is not None:
                result = {
                    **result,
                    "state": "alive" if relogin["state"] == "logged_in" else relogin["state"],
                    "login": relogin,
                }
        return result

    def _relogin_running(self, name: str, manual: bool) -> dict[str, Any] | None:
        """Sign in again in the running profile. Automatic triggers wait out a cooldown so a
        wrong password or a Google challenge is tried once, not in a loop."""
        from ..browser import login

        profile = self.pm.profiles.get(name)
        if profile is None or self.vault is None:
            return None
        now = time.time()
        with self._lock:
            if name in self._busy_login:
                return None
            if not manual and now - self._last_login.get(name, 0) < LOGIN_COOLDOWN:
                return None
            self._busy_login.add(name)
            self._last_login[name] = now
        try:
            mode = profile.login_mode
            password = totp_secret = None
            try:
                if "password" in profile.secrets:
                    password = self.vault.reveal(name, "password")
                if "totp_secret" in profile.secrets:
                    totp_secret = self.vault.reveal(name, "totp_secret")
            except Exception as e:
                result = {"state": "failed", "detail": f"vault: {e}"}
            else:
                from ..vault import vault as vault_mod

                code = (lambda: vault_mod.totp(totp_secret)[0]) if totp_secret else None
                result = login.sign_in(
                    self.launcher.control, name, profile.email or "", password, code, mode
                )
            state = {"logged_in": "alive", "needs_verification": "needs_verification"}.get(
                result["state"], "logged_out"
            )
            self.pm.update_meta(name, session_state=state, session_checked_at=time.time())
            self.log.add("relogin", name, state=result["state"], detail=result["detail"])
            return result
        finally:
            with self._lock:
                self._busy_login.discard(name)

    def relogin(self, name: str) -> dict[str, Any]:
        """Sign a profile back in now (the button); launches it first if it is closed."""
        profile = self.pm.profiles.get(name)
        if profile is None:
            raise AutomationError(f"profile {name} not found")
        launched_here = False
        try:
            if not self.launcher.is_running(name):
                if not self.launcher.start_thread(profile, lambda m: None):
                    raise AutomationError("could not start the profile")
                launched_here = True
                ok, error = self.launcher.wait_for_launch(name, LAUNCH_WAIT_TIMEOUT)
                if not ok:
                    raise AutomationError(f"launch failed: {error}")
            result = self._relogin_running(name, manual=True)
            if result is None:
                raise AutomationError("a login for this profile is already in progress")
            return result
        finally:
            if launched_here:
                self.launcher.stop_profile(name)

    def relogin_async(self, name: str) -> None:
        if name not in self.pm.profiles:
            raise AutomationError(f"profile {name} not found")

        def run() -> None:
            try:
                self.relogin(name)
            except Exception as e:
                self.log.add("relogin_error", name, error=str(e)[:200])

        self._pool.submit(run)

    def on_launched(self, name: str) -> None:
        """Launcher hook: a profile with auto-login on is checked as soon as it opens."""
        profile = self.pm.profiles.get(name)
        if profile is None or not getattr(profile, "auto_login", False):
            return

        def run() -> None:
            try:
                self._check_running(name)
            except Exception as e:
                self.log.add("session_check_error", name, error=str(e)[:200])

        threading.Thread(target=run, daemon=True).start()

    def check_session(self, name: str) -> dict[str, Any]:
        """Check one profile's Gmail session, launching it first if it is closed."""
        profile = self.pm.profiles.get(name)
        if profile is None:
            raise AutomationError(f"profile {name} not found")
        launched_here = False
        try:
            if not self.launcher.is_running(name):
                if not self.launcher.start_thread(profile, lambda m: None):
                    raise AutomationError("could not start the profile")
                launched_here = True
                ok, error = self.launcher.wait_for_launch(name, LAUNCH_WAIT_TIMEOUT)
                if not ok:
                    raise AutomationError(f"launch failed: {error}")
            return self._check_running(name)
        finally:
            if launched_here:
                self.launcher.stop_profile(name)

    def check_sessions(self, names: list[str]) -> dict[str, Any]:
        """Check several profiles in the background, a few at a time."""
        unknown = [n for n in names if n not in self.pm.profiles]
        if unknown:
            raise AutomationError(f"unknown profiles: {', '.join(unknown)}")

        def one(n: str) -> None:
            try:
                self.check_session(n)
            except Exception as e:
                self.log.add("session_check_error", n, error=str(e)[:200])

        for n in names:
            self._pool.submit(one, n)
        return {"started": names}

    # -- scheduler --
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="automation", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _loop(self) -> None:
        while not self._stop.wait(TICK_SECONDS):
            self.tick()

    def tick(self, now: float | None = None) -> list[str]:
        now = now or time.time()
        due = [
            t["id"]
            for t in self.tasks()
            if t["enabled"] and t.get("next_run") and t["next_run"] <= now
        ]
        started = []
        for task_id in due:
            try:
                self.run_task(task_id)
                started.append(task_id)
            except AutomationError:
                pass
        return started
