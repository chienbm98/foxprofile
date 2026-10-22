"""Push/pull encrypted profiles to a shared store so a login made on one machine
is reused on the others.

Each profile is two objects: `<name>.fpx` (encrypted archive) and `<name>.json`
(plain metadata with an integer version). There is no lock: a push is refused when
the store holds a newer version than the one this machine last synced, unless forced.
"""

from __future__ import annotations

import json
import os
import pathlib
import platform
import shutil
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Any

from ...core.config import (
    APP_ROOT,
    DATA_DIR,
    MACHINE_NAME,
    SYNC_AUTO,
    SYNC_LOG,
    SYNC_LOG_TEXT,
    SYNC_PASSPHRASE,
    SYNC_STATE_FILE,
    SYNC_URL,
)
from ...core.logging import get_logger
from ..automation.engine import ActivityLog
from .backends import Backend, FolderBackend, SyncError, _reachable, resolve_backend
from .crypto import DecryptError, decrypt_stream, encrypt_stream
from .logfmt import format_event, snapshot_text

if TYPE_CHECKING:
    from ...interfaces import IBrowserLauncher, IProfileManager

logger = get_logger("sync")


class SyncConflict(SyncError):
    pass


def _machine() -> str:
    return MACHINE_NAME or platform.node() or "unknown"


class SyncService:
    def __init__(
        self,
        pm: IProfileManager,
        launcher: IBrowserLauncher,
        backend: Backend | None = None,
        passphrase: str | None = None,
        state_file: str | None = None,
        data_dir: str | None = None,
        sync_log: str | None = None,
        app_root: str | None = None,
    ) -> None:
        self.pm = pm
        self.launcher = launcher
        self._backend = backend
        self._resolved = False
        self.log = ActivityLog(sync_log or SYNC_LOG)
        self._app_root = app_root
        self.store_label = ""
        self.passphrase = SYNC_PASSPHRASE if passphrase is None else passphrase
        self.state_file = pathlib.Path(state_file or SYNC_STATE_FILE)
        self.data_dir = data_dir or DATA_DIR
        self._lock = threading.RLock()

    @property
    def configured(self) -> bool:
        return bool(self.passphrase and (self._backend or SYNC_URL))

    @property
    def backend(self) -> Backend:
        """The store in use. A folder store (USB stick, LAN share) is looked up again when it
        has gone away, so plugging the stick back in or switching networks just works."""
        current = self._backend
        if current is not None and (
            not isinstance(current, FolderBackend) or not self._resolved or _reachable(current.root)
        ):
            return current
        if not SYNC_URL:
            if current is not None:
                return current
            raise SyncError("Sync is not configured: set FOXPROFILE_SYNC_URL")
        self._backend, self.store_label = resolve_backend(SYNC_URL)
        self._resolved = True
        return self._backend

    def _need_passphrase(self) -> None:
        if not self.passphrase:
            raise SyncError("Set FOXPROFILE_SYNC_PASSPHRASE to encrypt/decrypt synced profiles")

    def _state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_file)

    @property
    def _auto_file(self) -> pathlib.Path:
        return self.state_file.with_suffix(".auto.json")

    def auto_profiles(self) -> set[str]:
        try:
            return set(json.loads(self._auto_file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return set()

    def is_auto(self, name: str) -> bool:
        return name in self.auto_profiles()

    def set_auto(self, name: str, enabled: bool) -> bool:
        """Pull before launch and push after stop for this profile (API/server launches)."""
        with self._lock:
            names = self.auto_profiles()
            names.add(name) if enabled else names.discard(name)
            tmp = self._auto_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(sorted(names)), encoding="utf-8")
            os.replace(tmp, self._auto_file)
        return enabled

    def remote_meta(self, name: str) -> dict[str, Any] | None:
        raw = self.backend.read(f"{name}.json")
        return json.loads(raw) if raw else None

    def _record(
        self, event: str, name: str, trigger: str, started: float, ok: bool, **fields: Any
    ) -> None:
        """One line in sync_log.jsonl and one in the normal log: the data to tune sync from."""
        row = {
            "trigger": trigger,
            "ok": ok,
            "store": self.store_label or None,
            "machine": _machine(),
            "total_s": round(time.perf_counter() - started, 2),
            **fields,
        }
        self.log.add(event, name, **row)
        (logger.info if ok else logger.warning)("%s %s %s", event, name, row)
        if SYNC_LOG_TEXT:
            self._append_text_log({"t": time.time(), "event": event, "profile": name, **row})

    @property
    def app_root(self) -> str:
        return self._app_root or APP_ROOT or os.getcwd()

    @property
    def text_log_path(self) -> pathlib.Path:
        return pathlib.Path(self.app_root) / "sync-log.txt"

    def _append_text_log(self, event: dict[str, Any]) -> None:
        """sync-log.txt in the app's top folder: one readable line per action, kept to ~2 MB."""
        try:
            path = self.text_log_path
            if path.exists() and path.stat().st_size > 2_000_000:
                os.replace(path, path.with_suffix(".txt.1"))
            with path.open("a", encoding="utf-8") as f:
                f.write(format_event(event) + "\n")
        except OSError as e:
            logger.debug("Could not write %s: %s", self.text_log_path, e)

    def save_snapshot(self, limit: int = 500) -> pathlib.Path:
        """Write the latest events plus a status header to sync-log-<machine>-<time>.txt in the
        app's top folder and return the path."""
        try:
            profiles = self.status()
            store = self.store_label
        except Exception as e:  # the store may be away; the log is still worth saving
            profiles, store = [], f"unreachable: {e}"
        text = snapshot_text(
            self.log.tail(limit), {"machine": _machine(), "store": store, "profiles": profiles}
        )
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in _machine())
        path = pathlib.Path(self.app_root) / f"sync-log-{safe}-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def push(self, name: str, force: bool = False, trigger: str = "manual") -> dict[str, Any]:
        started = time.perf_counter()
        timing: dict[str, float] = {}
        try:
            meta = self._push(name, force, timing)
        except Exception as e:
            self._record(
                "sync_push",
                name,
                trigger,
                started,
                False,
                error=str(e)[:300],
                conflict=isinstance(e, SyncConflict),
                **timing,
            )
            raise
        self._record(
            "sync_push",
            name,
            trigger,
            started,
            True,
            version=meta["version"],
            bytes=meta["size"],
            **timing,
        )
        return meta

    def _push(self, name: str, force: bool, timing: dict[str, float]) -> dict[str, Any]:
        self._need_passphrase()
        with self._lock:
            profile = self.pm.profiles.get(name)
            if profile is None:
                raise SyncError(f"Profile '{name}' not found")
            if self.launcher.is_running(name):
                raise SyncError(f"Stop '{name}' before pushing it (its files are in use)")
            t = time.perf_counter()
            remote = self.remote_meta(name)
            timing["check_s"] = round(time.perf_counter() - t, 2)
            known = self._state().get(name, {}).get("version", 0)
            if remote and remote["version"] > known and not force:
                raise SyncConflict(
                    f"'{name}' was pushed from {remote.get('pushed_by')} "
                    f"(v{remote['version']}) after your last sync (v{known}); pull it first "
                    "or push with force"
                )
            from ..profile.transfer import export_to_zip

            with tempfile.TemporaryDirectory() as tmp:
                t = time.perf_counter()
                ok, zip_path = export_to_zip(
                    profile,
                    os.path.join(self.data_dir, name),
                    tmp,
                    True,
                    slim=True,
                    filename="p.zip",
                )
                timing["pack_s"] = round(time.perf_counter() - t, 2)
                if not ok:
                    raise SyncError(f"Export failed: {zip_path}")
                timing["pack_bytes"] = os.path.getsize(zip_path)
                enc = os.path.join(tmp, "p.fpx")
                t = time.perf_counter()
                with open(zip_path, "rb") as src, open(enc, "wb") as dst:
                    encrypt_stream(src, dst, self.passphrase)
                timing["encrypt_s"] = round(time.perf_counter() - t, 2)
                t = time.perf_counter()
                self.backend.upload(f"{name}.fpx", enc)
                timing["upload_s"] = round(time.perf_counter() - t, 2)
                size = os.path.getsize(enc)
            version = max(remote["version"] if remote else 0, known) + 1
            meta = {
                "name": name,
                "version": version,
                "pushed_at": time.time(),
                "pushed_by": _machine(),
                "size": size,
                "os_type": profile.os_type,
                "engine": profile.engine,
            }
            self.backend.write(f"{name}.json", json.dumps(meta).encode())
            state = self._state()
            state[name] = {"version": version, "synced_at": time.time()}
            self._save_state(state)
            logger.info("Pushed %s v%d (%d bytes)", name, version, size)
            return meta

    def push_after_stop(self, name: str) -> None:
        """Background push once a profile has stopped; coalesces the two stop paths."""
        time.sleep(2)  # let the browser release its files
        with self._lock:
            last = self._state().get(name, {}).get("synced_at", 0)
            if time.time() - last < 15:
                self.log.add(
                    "sync_push_skipped",
                    name,
                    trigger="auto-stop",
                    reason="already pushed seconds ago",
                )
                return
            try:
                self.push(name, trigger="auto-stop")
            except Exception as e:
                logger.warning("Auto-push of %s failed: %s", name, e)

    def pull(self, name: str, force: bool = False, trigger: str = "manual") -> dict[str, Any]:
        started = time.perf_counter()
        timing: dict[str, float] = {}
        try:
            meta = self._pull(name, force, timing)
        except Exception as e:
            self._record("sync_pull", name, trigger, started, False, error=str(e)[:300], **timing)
            raise
        self._record(
            "sync_pull",
            name,
            trigger,
            started,
            True,
            version=meta.get("version"),
            bytes=meta.get("size"),
            skipped=meta.get("skipped"),
            **timing,
        )
        return meta

    def _pull(self, name: str, force: bool, timing: dict[str, float]) -> dict[str, Any]:
        self._need_passphrase()
        with self._lock:
            t = time.perf_counter()
            remote = self.remote_meta(name)
            timing["check_s"] = round(time.perf_counter() - t, 2)
            if remote is None:
                raise SyncError(f"'{name}' is not in the sync store")
            known = self._state().get(name, {}).get("version", 0)
            exists = name in self.pm.profiles
            if exists and remote["version"] <= known and not force:
                return {**remote, "skipped": "already up to date"}
            if self.launcher.is_running(name):
                raise SyncError(f"Stop '{name}' before pulling it (its files are in use)")
            with tempfile.TemporaryDirectory() as tmp:
                enc, plain = os.path.join(tmp, "p.fpx"), os.path.join(tmp, "p.zip")
                t = time.perf_counter()
                self.backend.download(f"{name}.fpx", enc)
                timing["download_s"] = round(time.perf_counter() - t, 2)
                t = time.perf_counter()
                try:
                    with open(enc, "rb") as src, open(plain, "wb") as dst:
                        decrypt_stream(src, dst, self.passphrase)
                except DecryptError as e:
                    raise SyncError(str(e)) from e
                timing["decrypt_s"] = round(time.perf_counter() - t, 2)
                t = time.perf_counter()
                data_dir = pathlib.Path(self.data_dir) / name
                backup = pathlib.Path(self.data_dir) / f"{name}.syncbak"
                moved = False
                if data_dir.exists():
                    shutil.rmtree(backup, ignore_errors=True)
                    data_dir.rename(backup)
                    moved = True
                ok, result = self.pm.import_profile(plain, overwrite=True)
                if not ok:
                    if moved:
                        shutil.rmtree(data_dir, ignore_errors=True)
                        backup.rename(data_dir)
                    raise SyncError(f"Import failed: {result}")
                timing["import_s"] = round(time.perf_counter() - t, 2)
            state = self._state()
            state[name] = {"version": remote["version"], "synced_at": time.time()}
            self._save_state(state)
            logger.info("Pulled %s v%d", name, remote["version"])
            return remote

    def status(self) -> list[dict[str, Any]]:
        state = self._state()
        remote: dict[str, dict] = {}
        for key in self.backend.list():
            if key.endswith(".json"):
                try:
                    remote[key[:-5]] = json.loads(self.backend.read(key) or b"{}")
                except ValueError:
                    continue
        rows = []
        auto = self.auto_profiles()
        for name in sorted(set(remote) | set(self.pm.profiles)):
            r, local = remote.get(name), name in self.pm.profiles
            known = state.get(name, {}).get("version", 0)
            if r is None:
                st = "local-only"
            elif not local:
                st = "remote-only"
            elif r["version"] > known:
                st = "remote-newer"
            else:
                st = "synced"
            rows.append(
                {
                    "name": name,
                    "state": st,
                    "auto": name in auto,
                    "local_version": known,
                    "remote_version": r["version"] if r else None,
                    "pushed_by": r.get("pushed_by") if r else None,
                    "pushed_at": r.get("pushed_at") if r else None,
                }
            )
        return rows

    def remove_remote(self, name: str) -> None:
        self.backend.delete(f"{name}.fpx")
        self.backend.delete(f"{name}.json")

    def push_all(self, force: bool = False) -> dict[str, Any]:
        return self._each(list(self.pm.profiles), lambda n: self.push(n, force))

    def pull_all(self, force: bool = False) -> dict[str, Any]:
        names = [r["name"] for r in self.status() if r["remote_version"] is not None]
        return self._each(names, lambda n: self.pull(n, force))

    def _each(self, names, fn) -> dict[str, Any]:
        done, failed = [], {}
        for n in names:
            try:
                fn(n)
                done.append(n)
            except (SyncError, OSError) as e:
                failed[n] = str(e)
        return {"done": done, "failed": failed}


class AutoSyncHook:
    """Called by the browser launcher on every launch and stop, whoever triggers it
    (desktop app, panel, API, MCP, tasks). Acts only for profiles with auto-sync on."""

    def __init__(self, get_service) -> None:
        self._get = get_service

    def _active(self, name: str):
        svc = self._get()
        return svc if svc.configured and (SYNC_AUTO or svc.is_auto(name)) else None

    def before_launch(self, profile):
        svc = self._active(profile.name)
        if svc is None:
            return profile
        try:
            svc.pull(profile.name, trigger="auto-launch")
        except Exception as e:
            logger.warning("Auto-pull of %s skipped: %s", profile.name, e)
        return svc.pm.profiles.get(profile.name, profile)

    def after_stop(self, name: str) -> None:
        svc = self._active(name)
        if svc is not None:
            threading.Thread(target=svc.push_after_stop, args=(name,), daemon=True).start()
