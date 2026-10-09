from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ..theme.colors import COLORS
from ..theme.styles import ACCENT_STYLE, INK_STYLE

_WIDTH, _HEIGHT = 112, 36


def build_launch_button(
    name: str,
    is_loading: bool,
    is_running: bool,
    on_launch: Callable,
) -> ft.Button:
    """Create the context-aware Launch / Stop / Loading button."""
    if is_loading:
        return ft.Button(
            content=ft.ProgressRing(width=16, height=16, stroke_width=2, color=COLORS["text_sub"]),
            width=_WIDTH,
            height=_HEIGHT,
            disabled=True,
            tooltip=get_string("loading"),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                bgcolor=COLORS["paper_sunk"],
            ),
        )
    if is_running:
        return ft.Button(
            get_string("stop"),
            icon=ft.Icons.STOP_ROUNDED,
            width=_WIDTH,
            height=_HEIGHT,
            style=INK_STYLE,
            on_click=lambda _, n=name: on_launch(n),
        )
    return ft.Button(
        get_string("launch"),
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        width=_WIDTH,
        height=_HEIGHT,
        style=ACCENT_STYLE,
        on_click=lambda _, n=name: on_launch(n),
    )
