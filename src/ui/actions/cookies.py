import asyncio
import os
import pathlib
from collections.abc import Callable

import flet as ft

from ...core.config import DATA_DIR
from ...core.strings import get_string
from ...interfaces.protocols import IBrowserLauncher, IProfileManager
from ...services.browser import cookies, fingerprint
from ...services.browser.launcher import ProfileBusyError
from ..dialogs import open_confirm_dialog, open_cookie_dialog

_EXTENSIONS = {"json": "json", "netscape": "txt"}


def manage_cookies(
    page: ft.Page,
    name: str,
    file_picker: ft.FilePicker,
    pm: IProfileManager,
    bl: IBrowserLauncher,
    log: Callable[[str], None],
) -> None:
    profile = pm.profiles.get(name)
    if not profile:
        return
    if bl.is_running(name):
        log(get_string("cookie_stop_first", name=name))
        return

    profile_dir = os.path.join(DATA_DIR, name)

    def _locked(fn, arg):
        with bl.exclusive(name):
            return fn(name, profile.os_type, arg, engine=profile.engine)

    async def on_export(fmt: str) -> None:
        path = await file_picker.save_file(
            dialog_title=get_string(
                "cookie_export_json" if fmt == "json" else "cookie_export_netscape",
            ),
            file_name=f"{name}_cookies.{_EXTENSIONS[fmt]}",
            allowed_extensions=[_EXTENSIONS[fmt]],
        )
        if not path:
            return
        log(get_string("cookie_working", name=name))
        try:
            text, count = await asyncio.to_thread(_locked, cookies.export_cookies, fmt)
            pathlib.Path(path).write_text(text, encoding="utf-8")
        except (cookies.CookieError, OSError, ProfileBusyError) as e:
            log(get_string("cookie_error", name=name, error=e))
            return
        log(get_string("cookie_exported", name=name, count=count, path=path))

    async def on_import() -> None:
        files = await file_picker.pick_files(
            dialog_title=get_string("cookie_import"),
            allowed_extensions=["json", "txt"],
        )
        if not files or not files[0].path:
            return
        log(get_string("cookie_working", name=name))
        try:
            text = pathlib.Path(files[0].path).read_text(encoding="utf-8-sig")
            count = await asyncio.to_thread(_locked, cookies.import_cookies, text)
        except (cookies.CookieError, OSError, UnicodeDecodeError, ProfileBusyError) as e:
            log(get_string("cookie_error", name=name, error=e))
            return
        log(get_string("cookie_imported", name=name, count=count))

    def on_reset_fingerprint() -> None:
        def _do_reset() -> None:
            fingerprint.reset(profile_dir)
            log(get_string("fingerprint_was_reset", name=name))

        open_confirm_dialog(
            page,
            name,
            _do_reset,
            title=get_string("confirm_reset_fingerprint", name=name),
            action_label=get_string("fingerprint_reset"),
            action_icon=ft.Icons.FINGERPRINT,
        )

    info = fingerprint.summary(profile_dir)
    fingerprint_line = (
        get_string(
            "fingerprint_current",
            platform=info["platform"],
            screen=info["screen"],
            cores=info["hardware_concurrency"],
        )
        if info
        else get_string("fingerprint_none")
    )
    open_cookie_dialog(
        page,
        name,
        fingerprint_line,
        on_export,
        on_import,
        on_reset_fingerprint,
    )
