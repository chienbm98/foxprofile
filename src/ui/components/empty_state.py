from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ..theme.colors import COLORS, FONT_BOLD
from ..theme.styles import ACCENT_STYLE


def build_empty_state(on_create: Callable) -> ft.Container:
    """Shown when no profiles exist."""
    return ft.Container(
        alignment=ft.Alignment(0, 0),
        padding=ft.Padding.symmetric(vertical=64, horizontal=24),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
            tight=True,
            controls=[
                ft.Text(
                    get_string("no_profiles_yet"),
                    size=18,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(
                    get_string("create_profile_hint"),
                    size=14,
                    color=COLORS["text_sub"],
                    text_align=ft.TextAlign.CENTER,
                    width=420,
                ),
                ft.Container(height=12),
                ft.Button(
                    get_string("create_profile_btn"),
                    icon=ft.Icons.ADD,
                    height=40,
                    style=ACCENT_STYLE,
                    on_click=on_create,
                ),
            ],
        ),
    )
