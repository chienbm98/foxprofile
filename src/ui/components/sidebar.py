import os
from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ..theme.colors import COLORS
from ..theme.styles import ACCENT_STYLE, OUTLINE_STYLE

_LOGO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "logo.png"),
)


def build_sidebar(
    stats_text: ft.Text,
    running_text: ft.Text,
    _log_text: ft.Text,
    log_column: ft.Container,
    log_toggle_btn: ft.TextButton,
    on_new_profile: Callable,
    on_import: Callable,
    on_export: Callable,
    on_toggle_log: Callable,
    on_mcp: Callable,
    on_fullscreen_log: Callable,
) -> ft.Container:
    log_toggle_btn.on_click = on_toggle_log
    return ft.Container(
        width=310,
        bgcolor=COLORS["sidebar"],
        padding=ft.Padding.symmetric(horizontal=20, vertical=28),
        content=ft.Column(
            spacing=0,
            expand=True,
            controls=[
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Image(src=_LOGO, width=44, height=44),
                        ft.Column(
                            spacing=0,
                            controls=[
                                ft.Text(
                                    get_string("app_name"),
                                    size=26,
                                    weight=ft.FontWeight.BOLD,
                                    color=COLORS["text_main"],
                                ),
                                ft.Text(
                                    get_string("app_subtitle"),
                                    size=10,
                                    color=COLORS["accent"],
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ],
                        ),
                    ],
                ),
                ft.Divider(height=28, color=COLORS["border"]),
                ft.Button(
                    get_string("new_profile"),
                    icon=ft.Icons.ADD,
                    width=270,
                    height=44,
                    style=ACCENT_STYLE,
                    on_click=on_new_profile,
                ),
                ft.Container(height=14),
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.OutlinedButton(
                            get_string("import"),
                            icon=ft.Icons.DOWNLOAD,
                            width=116,
                            height=40,
                            style=OUTLINE_STYLE,
                            on_click=on_import,
                        ),
                        ft.OutlinedButton(
                            get_string("export"),
                            icon=ft.Icons.UPLOAD,
                            width=116,
                            height=40,
                            style=OUTLINE_STYLE,
                            on_click=on_export,
                        ),
                    ],
                ),
                ft.Container(height=10),
                ft.OutlinedButton(
                    get_string("mcp_button"),
                    icon=ft.Icons.SMART_TOY_OUTLINED,
                    width=242,
                    height=40,
                    style=OUTLINE_STYLE,
                    on_click=on_mcp,
                ),
                ft.Divider(height=24, color=COLORS["border"]),
                stats_text,
                ft.Container(height=6),
                running_text,
                ft.Container(height=16),
                ft.Divider(height=1, color=COLORS["border"]),
                ft.Container(height=10),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        log_toggle_btn,
                        ft.IconButton(
                            icon=ft.Icons.OPEN_IN_FULL,
                            icon_size=16,
                            icon_color=COLORS["text_sub"],
                            on_click=on_fullscreen_log,
                        ),
                    ],
                ),
                ft.Container(height=4),
                log_column,
            ],
        ),
    )
