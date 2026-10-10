from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ..theme.colors import COLORS, FONT_BOLD, FONT_DATA, FONT_MEDIUM, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, RAIL_STYLE

# (filter id, string key) in display order; counts come from the app.
FILTERS = (
    ("all", "filter_all"),
    ("running", "filter_running"),
    ("proxy", "filter_proxy"),
    ("direct", "filter_direct"),
    ("chrome", "filter_chrome"),
)


def build_filter_buttons(
    active: str, counts: dict[str, int], on_filter: Callable[[str], None]
) -> list[ft.Control]:
    """The rail's filter list; the active filter is set in cover ink."""
    controls: list[ft.Control] = []
    for fid, key in FILTERS:
        on = fid == active
        controls.append(
            ft.Container(
                height=36,
                border_radius=7,
                padding=ft.Padding.symmetric(horizontal=10),
                bgcolor=COLORS["cover_ink"] if on else None,
                ink=True,
                on_click=lambda _, f=fid: on_filter(f),
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            get_string(key),
                            size=13.5,
                            font_family=FONT_SEMIBOLD if on else FONT_MEDIUM,
                            color=COLORS["sidebar"] if on else COLORS["cover_ink"],
                        ),
                        ft.Text(
                            str(counts.get(fid, 0)),
                            size=12,
                            font_family=FONT_DATA,
                            color=COLORS["sidebar"] if on else COLORS["cover_muted"],
                        ),
                    ],
                ),
            )
        )
    return controls


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
    filter_column: ft.Column | None = None,
    language: str = "en",
    on_language: Callable[[str], None] | None = None,
) -> ft.Container:
    log_toggle_btn.on_click = on_toggle_log
    return ft.Container(
        width=240,
        bgcolor=COLORS["sidebar"],
        # The tile is rendered at 2x; scale 2 draws it at its authored size.
        image=ft.DecorationImage(src="rail-guilloche.png", repeat=ft.ImageRepeat.REPEAT, scale=2),
        padding=ft.Padding.only(left=16, right=16, top=22, bottom=16),
        content=ft.Column(
            spacing=0,
            expand=True,
            controls=[
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Image(src="logo.png", width=34, height=34),
                        ft.Column(
                            spacing=0,
                            controls=[
                                ft.Text(
                                    get_string("app_name"),
                                    size=18,
                                    font_family=FONT_BOLD,
                                    color=COLORS["cover_ink"],
                                ),
                                ft.Text(
                                    get_string("app_subtitle"),
                                    size=12,
                                    color=COLORS["cover_muted"],
                                ),
                            ],
                        ),
                    ],
                ),
                ft.Container(height=10),
                stats_text,
                ft.Container(height=2),
                running_text,
                ft.Container(height=10),
                ft.Button(
                    get_string("new_profile"),
                    icon=ft.Icons.ADD,
                    width=208,
                    height=42,
                    style=ACCENT_STYLE,
                    on_click=on_new_profile,
                ),
                ft.Container(height=10),
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.OutlinedButton(
                            get_string("import"),
                            icon=ft.Icons.FILE_DOWNLOAD_OUTLINED,
                            expand=True,
                            height=36,
                            style=RAIL_STYLE,
                            on_click=on_import,
                        ),
                        ft.OutlinedButton(
                            get_string("export"),
                            icon=ft.Icons.FILE_UPLOAD_OUTLINED,
                            expand=True,
                            height=36,
                            style=RAIL_STYLE,
                            on_click=on_export,
                        ),
                    ],
                ),
                ft.Container(height=22),
                ft.Container(
                    padding=ft.Padding.only(left=10, bottom=6),
                    content=ft.Text(
                        get_string("filter_title"),
                        size=12,
                        font_family=FONT_SEMIBOLD,
                        color=COLORS["cover_muted"],
                    ),
                ),
                filter_column or ft.Column(),
                ft.Container(expand=True),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        log_toggle_btn,
                        ft.IconButton(
                            icon=ft.Icons.OPEN_IN_FULL,
                            icon_size=16,
                            icon_color=COLORS["cover_muted"],
                            tooltip=get_string("activity_log"),
                            on_click=on_fullscreen_log,
                        ),
                    ],
                ),
                log_column,
                ft.Container(height=8),
                ft.OutlinedButton(
                    get_string("mcp_button"),
                    icon=ft.Icons.SMART_TOY_OUTLINED,
                    width=208,
                    height=38,
                    style=RAIL_STYLE,
                    on_click=on_mcp,
                ),
                ft.Container(height=8),
                _language_switch(language, on_language),
            ],
        ),
    )


def _language_switch(active: str, on_language: Callable[[str], None] | None) -> ft.Container:
    """Segmented Tiếng Việt / English switch, as in the web panel."""

    def seg(code: str, label: str) -> ft.Container:
        on = code == active
        return ft.Container(
            expand=True,
            height=30,
            border_radius=6,
            alignment=ft.Alignment(0, 0),
            bgcolor=COLORS["sidebar"] if on else None,
            ink=not on,
            on_click=None if on or on_language is None else (lambda _, c=code: on_language(c)),
            content=ft.Text(
                label,
                size=13,
                font_family=FONT_SEMIBOLD if on else FONT_MEDIUM,
                color=COLORS["cover_ink"] if on else COLORS["cover_muted"],
            ),
        )

    return ft.Container(
        padding=3,
        border_radius=8,
        bgcolor=COLORS["cover_deep"],
        content=ft.Row(spacing=0, controls=[seg("vi", "Tiếng Việt"), seg("en", "English")]),
    )
