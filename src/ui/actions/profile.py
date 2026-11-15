from collections.abc import Callable

import flet as ft

from ...core.errors import ProfileBusyError, ProfileStoreError
from ...core.strings import get_string
from ...interfaces.protocols import IBrowserLauncher, IProfileManager, IProxyService
from ...services.browser import chrome_prefetch
from ..dialogs import open_confirm_dialog, open_profile_dialog
from ..dialogs.profile import ProfileDraft
from .errors import failure_message


def delete_profile(
    page: ft.Page,
    name: str,
    pm: IProfileManager,
    log: Callable[[str], None],
    refresh: Callable[[], None],
) -> None:
    def do_delete() -> None:
        try:
            pm.delete_profile(name)
        except (ProfileBusyError, ProfileStoreError) as e:
            log(failure_message(name, e))
            return
        log(get_string("deleted_profile", name=name))
        refresh()

    open_confirm_dialog(page, name, do_delete)


def edit_profile(
    page: ft.Page,
    name: str,
    pm: IProfileManager,
    bl: IBrowserLauncher,
    ps: IProxyService,
    log: Callable[[str], None],
    refresh: Callable[[], None],
) -> None:
    profile = pm.profiles.get(name)
    if not profile:
        return
    original = profile.name

    def on_save(draft: ProfileDraft) -> str | None:
        if draft.name != original and bl.is_running(original):
            return get_string("stop_before_rename")
        proton_args = {}
        if draft.proxy_mode == "proton":
            proton_args = {
                "proton_user": draft.proton_user,
                "proton_password": draft.proton_password or None,
                "proton_totp": draft.proton_totp or None,
                "proton_country": draft.proton_country,
            }
        try:
            updated = pm.update_profile(
                original,
                draft.name,
                draft.proxy,
                draft.os_type,
                draft.timezone,
                draft.locale,
                new_proxy_mode=draft.proxy_mode,
                **proton_args,
            )
        except (ProfileBusyError, ProfileStoreError) as e:
            return failure_message(original, e)
        if updated:
            log(get_string("updated_profile", old=original, new=draft.name))
            refresh()
            return None
        return get_string("update_failed")

    open_profile_dialog(page, ps, on_save, profile)


def add_profile(
    page: ft.Page,
    pm: IProfileManager,
    ps: IProxyService,
    log: Callable[[str], None],
    refresh: Callable[[], None],
) -> None:
    def on_save(draft: ProfileDraft) -> str | None:
        if draft.engine == "chrome" and (reason := chrome_prefetch.unsupported_reason()):
            return get_string("chrome_engine_unsupported", reason=reason)
        try:
            created = pm.add_profile(
                draft.name,
                draft.proxy,
                draft.os_type,
                draft.timezone,
                draft.locale,
                draft.engine,
                proxy_mode=draft.proxy_mode,
                proton_user=draft.proton_user,
                proton_password=draft.proton_password,
                proton_totp=draft.proton_totp,
                proton_country=draft.proton_country,
            )
        except ProfileStoreError as e:
            return failure_message(draft.name, e)
        if created:
            log(get_string("created_profile", name=draft.name))
            if draft.engine == "chrome":
                chrome_prefetch.start(log)
            refresh()
            return None
        return get_string("profile_exists")

    open_profile_dialog(page, ps, on_save)
