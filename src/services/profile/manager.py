import contextlib
import dataclasses
import json
import os
import pathlib
import shutil
import threading
import time
from collections.abc import Callable

from ...core import config
from ...core.errors import ProfileAccountSaveError, ProfileStoreError, ProtonStoreError
from ...core.logging import get_logger
from ...models.profile import (
    ENGINES,
    OS_TYPES,
    PROXY_MODES,
    Profile,
    country_or_none,
    extension_or_none,
    proxy_mode_or_default,
)
from ...services import proton_account
from ...utils.validation import (
    valid_or_none,
    validate_locale,
    validate_profile_name,
    validate_timezone,
)
from .transfer import export_to_zip, import_from_zip, read_profile_meta

logger = get_logger("profile.manager")

# Holds one profile's data directory for the duration of an operation. It raises
# ProfileBusyError while that profile's browser is running or busy.
Exclusive = Callable[[str], contextlib.AbstractContextManager]


def _engine_or_default(value: object) -> str:
    return value if value in ENGINES else "camoufox"


def _replace(src: pathlib.Path, dst: pathlib.Path, attempts: int = 10) -> None:
    """os.replace, retried briefly: on Windows it fails with a sharing violation
    while another process (antivirus, indexer, a reader) has the target open."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.02 * (i + 1))


def _no_guard(_name: str) -> contextlib.AbstractContextManager:
    return contextlib.nullcontext()


class ProfileManager:
    def __init__(self, exclusive: Exclusive | None = None) -> None:
        """`exclusive` guards destructive operations against a running browser.

        The container passes the launcher's guard. Without one (tests, scripts)
        nothing is guarded.
        """
        self._lock = threading.RLock()
        self._exclusive: Exclusive = exclusive or _no_guard
        self.profiles: dict[str, Profile] = {}
        self._load_profiles()
        pathlib.Path(config.DATA_DIR).mkdir(exist_ok=True, parents=True)

    def _find_by_casefold(self, name: str) -> str | None:
        """Return the existing profile key that case-folds to *name*, or None.

        Used to enforce case-insensitive uniqueness across all platforms so that
        a profiles.json exported on Linux (case-sensitive FS) can be imported on
        Windows/macOS (case-insensitive FS) without data-dir collisions.
        """
        lower = name.casefold()
        return next((k for k in self.profiles if k.casefold() == lower), None)

    def _data_path(self, name: str) -> str:
        return config.profile_data_dir(name)

    def _load_profiles(self) -> None:
        path = pathlib.Path(config.PROFILES_FILE)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("the top level must be a JSON object")
        except (OSError, ValueError) as e:
            # Keep the unreadable file: the next save would otherwise replace it
            # with an empty list and lose every profile in it.
            backup = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
            with contextlib.suppress(OSError):
                shutil.copy2(path, backup)
            logger.error(
                "Could not read %s (%s); starting empty. Kept a copy at %s", path, e, backup
            )
            return
        for name, p_data in data.items():
            try:
                if (
                    not isinstance(p_data, dict)
                    or not validate_profile_name(name)[0]
                    or p_data.get("name") != name
                ):
                    logger.warning("Skipping profile with unsafe name: %r", name)
                    continue
                os_type = p_data.get("os_type", p_data.get("config", {}).get("os", "windows"))
                clean_data = {
                    "name": p_data.get("name"),
                    "proxy": p_data.get("proxy"),
                    "os_type": os_type if os_type in OS_TYPES else "windows",
                    "timezone": valid_or_none(p_data.get("timezone"), validate_timezone),
                    "locale": valid_or_none(p_data.get("locale"), validate_locale),
                    "engine": _engine_or_default(p_data.get("engine")),
                    "extension": extension_or_none(p_data.get("extension")),
                    "proton_country": country_or_none(p_data.get("proton_country")),
                }
                mode = proxy_mode_or_default(
                    p_data.get("proxy_mode"),
                    clean_data["proxy"],
                    clean_data["extension"],
                )
                clean_data["proxy_mode"] = mode
                clean_data["extension"] = "proton-vpn" if mode == "proton" else None
                if mode != "proxy":
                    clean_data["proxy"] = None
                self.profiles[name] = Profile(**clean_data)
            except (AttributeError, TypeError) as e:
                logger.warning("Skipping unreadable profile %r: %s", name, e)
        logger.info("Loaded %d profiles", len(self.profiles))

    def save_profiles(self) -> None:
        """Atomic write of profiles.json. Raises ProfileStoreError if it cannot be written."""
        path = pathlib.Path(config.PROFILES_FILE)
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(
                json.dumps(
                    {name: p.to_dict() for name, p in self.profiles.items()},
                    indent=4,
                ),
                encoding="utf-8",
            )
            _replace(tmp, path)
        except OSError as e:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            logger.exception("Error saving profiles: %s", e)
            raise ProfileStoreError(f"Could not write {path.name}: {e.strerror or e}") from e
        logger.debug("Profiles saved")

    def _snapshot(self) -> dict[str, Profile]:
        return {name: dataclasses.replace(p) for name, p in self.profiles.items()}

    def _restore(self, snapshot: dict[str, Profile]) -> None:
        self.profiles.clear()
        self.profiles.update(snapshot)

    def _save_proton(self, name: str, user: str, password: str | None, totp: str | None) -> None:
        try:
            proton_account.save(name, user, password, totp)
        except (OSError, ProtonStoreError) as e:
            logger.warning("The Proton account of %s was not saved: %s", name, e)
            raise ProfileAccountSaveError(
                f"The profile was saved, but its Proton account was not: {e}"
            ) from e

    def _forget_account(self, name: str) -> None:
        try:
            proton_account.clear(name)
        except OSError as e:
            logger.warning("The Proton account of %s could not be cleared: %s", name, e)

    def add_profile(
        self,
        name: str,
        proxy: str,
        os_type: str,
        timezone: str | None = None,
        locale: str | None = None,
        engine: str = "camoufox",
        proxy_mode: str | None = None,
        proton_user: str = "",
        proton_password: str = "",
        proton_totp: str = "",
        proton_country: str = "",
    ) -> bool:
        with self._lock:
            if self._find_by_casefold(name) is not None:
                return False
            # Create directory before touching profiles.json so a mkdir failure
            # does not leave an entry with no data dir on disk.
            try:
                pathlib.Path(self._data_path(name)).mkdir(exist_ok=True, parents=True)
            except OSError as e:
                logger.warning("Could not create data dir for %s: %s", name, e)
                return False
            mode = proxy_mode if proxy_mode in PROXY_MODES else ("proxy" if proxy else "direct")
            saved = self._snapshot()
            self.profiles[name] = Profile(
                name=name,
                proxy=(proxy or None) if mode == "proxy" else None,
                os_type=os_type,
                timezone=timezone or None,
                locale=locale or None,
                engine=engine,
                extension="proton-vpn" if mode == "proton" else None,
                proxy_mode=mode,
                proton_country=country_or_none(proton_country),
            )
            try:
                self.save_profiles()
            except ProfileStoreError:
                self._restore(saved)
                raise
            if mode == "proton" and proton_user.strip():
                self._save_proton(name, proton_user, proton_password or None, proton_totp or None)
            logger.info("Created profile: %s", name)
            return True

    def update_profile(
        self,
        original_name: str,
        new_name: str,
        new_proxy: str,
        new_os: str,
        new_timezone: str | None = None,
        new_locale: str | None = None,
        new_proxy_mode: str | None = None,
        proton_user: str | None = None,
        proton_password: str | None = None,
        proton_totp: str | None = None,
        proton_country: str | None = None,
    ) -> bool:
        """Replace every field; a None/empty timezone or locale means automatic.

        A rename moves the data directory, so the profile must not be running.
        """
        renaming = new_name != original_name
        guard = self._exclusive(original_name) if renaming else contextlib.nullcontext()
        with guard, self._lock:
            if original_name not in self.profiles:
                return False

            if renaming:
                # Case-insensitive uniqueness: a case-only rename of the profile
                # itself is allowed; renaming to another profile's casefold is not.
                conflicting = self._find_by_casefold(new_name)
                if conflicting is not None and conflicting != original_name:
                    return False

            saved = self._snapshot()
            moved = False
            # Rename the data directory BEFORE mutating in-memory state so that
            # an OSError leaves memory and JSON untouched.
            if renaming:
                old_dir = pathlib.Path(self._data_path(original_name))
                new_dir = pathlib.Path(self._data_path(new_name))
                if old_dir.exists():
                    if new_dir.exists():
                        # On case-insensitive filesystems (Windows/macOS) a
                        # case-only rename sees the target as existing because
                        # both paths point to the same directory entry.  Allow
                        # the rename only in that situation.
                        try:
                            same = old_dir.samefile(new_dir)
                        except OSError:
                            same = False
                        if not same:
                            # Refuse: do NOT delete potential user data.
                            logger.warning(
                                "Cannot rename %s -> %s: target data dir already exists",
                                original_name,
                                new_name,
                            )
                            return False
                    try:
                        old_dir.rename(new_dir)
                    except OSError as e:
                        logger.warning("Could not rename data dir for %s: %s", original_name, e)
                        return False
                    moved = True

            profile = self.profiles[original_name]
            mode = (
                new_proxy_mode
                if new_proxy_mode in PROXY_MODES
                else ("proxy" if new_proxy else "direct")
            )
            profile.name = new_name
            profile.proxy = (new_proxy or None) if mode == "proxy" else None
            profile.os_type = new_os
            profile.timezone = new_timezone or None
            profile.locale = new_locale or None
            profile.proxy_mode = mode
            profile.extension = "proton-vpn" if mode == "proton" else None
            if mode == "proton" and proton_country is not None:
                profile.proton_country = country_or_none(proton_country)

            if renaming:
                del self.profiles[original_name]
                self.profiles[new_name] = profile

            try:
                self.save_profiles()
            except ProfileStoreError:
                self._restore(saved)
                if moved:
                    with contextlib.suppress(OSError):
                        pathlib.Path(self._data_path(new_name)).rename(
                            self._data_path(original_name)
                        )
                raise

            if renaming:
                try:
                    proton_account.rename(original_name, new_name)
                except (OSError, ProtonStoreError) as e:
                    logger.warning("The Proton account of %s was not moved: %s", original_name, e)
                    raise ProfileAccountSaveError(
                        f"The profile was renamed, but its Proton account was not moved: {e}"
                    ) from e
            if mode == "proton" and proton_user is not None:
                self._save_proton(new_name, proton_user, proton_password, proton_totp)

            logger.info("Updated profile: %s -> %s", original_name, new_name)
            return True

    def set_proton_country(self, name: str, country: str) -> bool:
        """Store the Proton exit country for a profile ("" = Quick Connect)."""
        with self._lock:
            profile = self.profiles.get(name)
            if profile is None:
                return False
            previous = profile.proton_country
            profile.proton_country = country_or_none(country)
            try:
                self.save_profiles()
            except ProfileStoreError:
                profile.proton_country = previous
                raise
            return True

    def delete_profile(self, name: str) -> bool:
        with self._exclusive(name), self._lock:
            if name not in self.profiles:
                return False
            saved = self._snapshot()
            del self.profiles[name]
            try:
                self.save_profiles()
            except ProfileStoreError:
                self._restore(saved)
                raise
            # The data goes only after the profile is gone from profiles.json: a
            # failed save must never leave a registered profile without its data.
            self._forget_account(name)
            # Inside the lock: a profile re-created under the same (or, on a
            # case-insensitive file system, a case-variant) name must not have
            # its fresh data dir removed by this delete.
            shutil.rmtree(self._data_path(name), ignore_errors=True)
        logger.info("Deleted profile: %s", name)
        return True

    def list_profiles(self) -> list[Profile]:
        with self._lock:
            return list(self.profiles.values())

    def export_profile(
        self,
        name: str,
        export_path: str,
        include_data: bool = True,
    ) -> tuple[bool, str]:
        # Copying the data of a running browser yields files caught mid-write, so
        # the data is exported only while the profile is stopped.
        guard = self._exclusive(name) if include_data else contextlib.nullcontext()
        with guard:
            with self._lock:
                if name not in self.profiles:
                    return False, "Profile not found"
                profile = dataclasses.replace(self.profiles[name])
            return export_to_zip(profile, self._data_path(name), export_path, include_data)

    def import_profile(
        self,
        zip_path: str,
        overwrite: bool = False,
    ) -> tuple[bool, str]:
        # Decide before extracting: an archive must not write into an existing
        # profile's data unless overwriting, and an overwrite that changes the
        # engine starts from an empty directory (the engines' data do not mix).
        meta = read_profile_meta(zip_path) or {}
        name = meta.get("name")
        with self._lock:
            # Case-insensitive collision check: find any existing profile whose
            # name casefolds to the imported name so the check is consistent on
            # all platforms (Windows/macOS case-insensitive FS, Linux sensitive).
            existing_key = self._find_by_casefold(name) if name else None
            if existing_key is not None and not overwrite:
                return False, f"Profile '{name}' already exists"
            guard = (
                self._exclusive(existing_key)
                if existing_key is not None
                else contextlib.nullcontext()
            )
            with guard:
                return self._import_locked(zip_path, meta, existing_key)

    def _import_locked(
        self,
        zip_path: str,
        meta: dict,
        existing_key: str | None,
    ) -> tuple[bool, str]:
        if existing_key is not None and (meta.get("engine") or "camoufox") != (
            self.profiles[existing_key].engine
        ):
            shutil.rmtree(self._data_path(existing_key), ignore_errors=True)

        success, result = import_from_zip(zip_path, config.DATA_DIR)
        if not success:
            return False, result

        profile = result
        saved = self._snapshot()
        # An overwrite under a different case replaces the old entry rather
        # than leaving two names for one data directory.
        if existing_key is not None and existing_key != profile.name:
            old_dir = pathlib.Path(self._data_path(existing_key))
            new_dir = pathlib.Path(self._data_path(profile.name))
            if old_dir.exists() and not (new_dir.exists() and old_dir.samefile(new_dir)):
                shutil.rmtree(old_dir, ignore_errors=True)
            del self.profiles[existing_key]
        self.profiles[profile.name] = profile
        try:
            self.save_profiles()
        except ProfileStoreError:
            self._restore(saved)
            raise
        # Credentials are never part of a profile archive; drop a stale entry for
        # the same name so the imported profile cannot inherit it.
        self._forget_account(profile.name)
        logger.info("Registered imported profile: %s", profile.name)
        return True, profile.name
