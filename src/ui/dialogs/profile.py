import threading
from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ...interfaces.protocols import IProxyService
from ...models.profile import Profile
from ...services.proxy.geo_check import GeoCheckResult, check_geo
from ...utils.validation import (
    validate_locale,
    validate_profile_name,
    validate_proxy_format,
    validate_timezone,
)
from ..theme.colors import COLORS
from ..theme.page import build_os_dropdown
from ..theme.styles import ACCENT_STYLE, DLG_FIELD_KWARGS, OUTLINE_STYLE


def open_profile_dialog(
    page: ft.Page,
    proxy_service: IProxyService,
    on_save: Callable[[str, str, str, str, str], str | None],
    profile: Profile | None = None,
) -> None:
    is_edit = profile is not None
    title = get_string("edit_profile") if is_edit else get_string("create_new_profile")
    subtitle = (
        get_string("editing_profile", name=profile.name)
        if profile is not None
        else get_string("configure_identity")
    )
    save_label = get_string("save_changes") if is_edit else get_string("create_profile_btn")
    save_icon = ft.Icons.SAVE if is_edit else ft.Icons.ADD

    name_field = ft.TextField(
        label=get_string("profile_name"),
        value=profile.name if profile is not None else "",
        hint_text="" if profile is not None else get_string("enter_profile_name"),
        **DLG_FIELD_KWARGS,
    )
    proxy_field = ft.TextField(
        label=get_string("proxy_optional"),
        value=(profile.proxy or "") if profile is not None else "",
        hint_text=get_string("proxy_hint"),
        **DLG_FIELD_KWARGS,
    )
    os_dropdown = build_os_dropdown(
        profile.os_type if profile is not None else "windows",
    )
    timezone_field = ft.TextField(
        label=get_string("timezone_optional"),
        value=(profile.timezone or "") if profile is not None else "",
        hint_text=get_string("timezone_hint"),
        expand=3,
        **DLG_FIELD_KWARGS,
    )
    locale_field = ft.TextField(
        label=get_string("locale_optional"),
        value=(profile.locale or "") if profile is not None else "",
        hint_text=get_string("locale_hint"),
        expand=2,
        **DLG_FIELD_KWARGS,
    )
    geo_error = ft.Text("", size=12, color=COLORS["error"], visible=False)
    geo_result = ft.Column(spacing=4, visible=False)
    name_error = ft.Text("", size=12, color=COLORS["error"], visible=False)
    proxy_error = ft.Text("", size=12, color=COLORS["error"], visible=False)
    check_btn = ft.OutlinedButton(
        get_string("check_proxy"),
        icon=ft.Icons.WIFI_FIND,
        height=38,
        style=OUTLINE_STYLE,
    )

    ip_btn = ft.OutlinedButton(
        get_string("check_ip"),
        icon=ft.Icons.PUBLIC,
        height=38,
        style=OUTLINE_STYLE,
    )
    ip_btn.on_click = lambda _: _do_ip_check(
        page, proxy_field, timezone_field, locale_field, geo_result, ip_btn
    )

    check_btn.on_click = lambda _: _do_proxy_check(
        page,
        proxy_field,
        proxy_error,
        check_btn,
        proxy_service,
    )

    def on_submit(_: ft.ControlEvent) -> None:
        name = (name_field.value or "").strip()
        proxy = (proxy_field.value or "").strip()
        os_type = os_dropdown.value or "windows"
        timezone = (timezone_field.value or "").strip()
        locale = (locale_field.value or "").strip()
        name_error.visible = proxy_error.visible = geo_error.visible = False

        valid_name, name_err = validate_profile_name(name)
        if not valid_name:
            name_error.value = name_err
            name_error.visible = True
            page.update()
            return

        valid_proxy, proxy_err = validate_proxy_format(proxy)
        if not valid_proxy:
            proxy_error.value = proxy_err
            proxy_error.visible = True
            page.update()
            return

        for validate, value in ((validate_timezone, timezone), (validate_locale, locale)):
            valid, geo_err = validate(value)
            if not valid:
                geo_error.value = geo_err
                geo_error.visible = True
                page.update()
                return

        error = on_save(name, proxy, os_type, timezone, locale)
        if error:
            name_error.value = error
            name_error.visible = True
            page.update()
        else:
            page.pop_dialog()

    dlg = ft.AlertDialog(
        modal=True,
        bgcolor=COLORS["card_bg"],
        title=ft.Text(
            title,
            size=22,
            weight=ft.FontWeight.BOLD,
            color=COLORS["text_main"],
        ),
        content=ft.Container(
            width=420,
            content=ft.Column(
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text(subtitle, size=13, color=COLORS["text_sub"]),
                    ft.Container(height=14),
                    name_field,
                    name_error,
                    ft.Container(height=6),
                    proxy_field,
                    proxy_error,
                    ft.Row(spacing=8, controls=[check_btn, ip_btn]),
                    ft.Container(height=6),
                    os_dropdown,
                    ft.Container(height=6),
                    ft.Row(spacing=8, controls=[timezone_field, locale_field]),
                    geo_error,
                    geo_result,
                    ft.Container(height=14),
                ],
            ),
        ),
        actions=[
            ft.TextButton(
                get_string("cancel"),
                style=ft.ButtonStyle(color=COLORS["text_sub"]),
                on_click=lambda _: page.pop_dialog(),
            ),
            ft.Button(
                save_label,
                icon=save_icon,
                style=ACCENT_STYLE,
                on_click=on_submit,
            ),
        ],
    )
    page.show_dialog(dlg)


def _do_proxy_check(
    page: ft.Page,
    proxy_field: ft.TextField,
    proxy_error: ft.Text,
    check_btn: ft.OutlinedButton,
    proxy_service: IProxyService,
) -> None:
    proxy = (proxy_field.value or "").strip()
    if not proxy:
        proxy_error.value = get_string("enter_proxy_to_check")
        proxy_error.color = COLORS["warning"]
        proxy_error.visible = True
        page.update()
        return

    check_btn.content = ft.Text(get_string("proxy_checking"))
    check_btn.disabled = True
    proxy_error.visible = False
    page.update()

    def do_check() -> None:
        success, message = proxy_service.check_proxy_sync(proxy)
        check_btn.content = ft.Text(get_string("check_proxy"))
        check_btn.disabled = False
        proxy_error.value = message
        proxy_error.color = COLORS["success"] if success else COLORS["error"]
        proxy_error.visible = True
        page.update()

    threading.Thread(target=do_check, daemon=True).start()


def _do_ip_check(
    page: ft.Page,
    proxy_field: ft.TextField,
    timezone_field: ft.TextField,
    locale_field: ft.TextField,
    geo_result: ft.Column,
    ip_btn: ft.OutlinedButton,
) -> None:
    proxy = (proxy_field.value or "").strip()
    timezone = (timezone_field.value or "").strip()
    locale = (locale_field.value or "").strip()
    for validate, value in (
        (validate_proxy_format, proxy),
        (validate_timezone, timezone),
        (validate_locale, locale),
    ):
        valid, err = validate(value)
        if not valid:
            geo_result.controls = [ft.Text(err, size=12, color=COLORS["error"])]
            geo_result.visible = True
            page.update()
            return

    ip_btn.content = ft.Text(get_string("ip_checking"))
    ip_btn.disabled = True
    geo_result.visible = False
    page.update()

    def use_locale(value: str) -> None:
        locale_field.value = value
        page.update()

    def do_check() -> None:
        try:
            result = check_geo(proxy or None, timezone or None, locale or None)
            geo_result.controls = _geo_lines(result, use_locale)
        except Exception as e:
            geo_result.controls = [
                ft.Text(get_string("geo_check_failed", error=e), size=12, color=COLORS["error"])
            ]
        ip_btn.content = ft.Text(get_string("check_ip"))
        ip_btn.disabled = False
        geo_result.visible = True
        page.update()

    threading.Thread(target=do_check, daemon=True).start()


def _geo_lines(result: GeoCheckResult, use_locale: Callable[[str], None]) -> list[ft.Control]:
    def line(text: str, color: str = COLORS["text_sub"]) -> ft.Text:
        return ft.Text(text, size=12, color=color, selectable=True)

    if result.exit_ip is None:
        return [line(get_string("geo_check_failed", error=result.error), COLORS["error"])]

    mode = {True: get_string("geo_pinned"), False: get_string("geo_auto")}
    lines: list[ft.Control] = [
        line(
            get_string("geo_exit", ip=result.exit_ip, country=result.country or "?"),
            COLORS["text_main"],
        ),
        line(
            get_string(
                "geo_timezone", value=result.timezone or "?", mode=mode[result.timezone_pinned]
            )
        ),
        line(
            get_string(
                "geo_locale",
                value=result.locale or f"~{result.suggested_locale or '?'}",
                mode=mode[True] if result.locale_pinned else get_string("geo_locale_random"),
            )
        ),
    ]
    for s in result.sources:
        if s.error:
            lines.append(
                line(
                    get_string("geo_source_error", source=s.source, error=s.error),
                    COLORS["text_dim"],
                )
            )
        else:
            lines.append(
                line(
                    get_string(
                        "geo_source",
                        source=s.source,
                        ip=s.ip or "?",
                        country=s.country or "?",
                        city=s.city or "",
                        timezone=s.timezone or "-",
                    ),
                    COLORS["text_dim"],
                )
            )
    if result.error:
        lines.append(line(result.error, COLORS["error"]))
    for w in result.warnings:
        lines.append(line(f"\u26a0 {w.message}", COLORS["warning"]))
    if not result.warnings and not result.error:
        lines.append(line(f"\u2713 {get_string('geo_all_good')}", COLORS["success"]))
    if result.suggested_locale and not result.locale_pinned:
        lines.append(
            ft.TextButton(
                get_string("geo_use_suggested", value=result.suggested_locale),
                on_click=lambda _, v=result.suggested_locale: use_locale(v),
            )
        )
    return lines
