from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ...models.profile import Profile
from ..state import AppState
from ..theme.colors import COLORS, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, OUTLINE_STYLE

BulkCallbacks = dict[str, Callable[[], None]]


def rebuild_bulk_bar(
    bulk_bar: ft.Row,
    state: AppState,
    page_profiles: list[Profile],
    cbs: BulkCallbacks,
) -> None:
    count = len(state.selected_names())
    if count == 0:
        bulk_bar.visible = False
        bulk_bar.controls = []
        return
    bulk_bar.visible = True
    bulk_bar.controls = [_build_container(count, cbs)]


def _build_container(count: int, cbs: BulkCallbacks) -> ft.Container:
    def btn(label: str, icon: str, key: str, style: ft.ButtonStyle) -> ft.Control:
        cls = ft.Button if style is ACCENT_STYLE else ft.OutlinedButton
        return cls(label, icon=icon, height=32, style=style, on_click=lambda _: cbs[key]())

    return ft.Container(
        expand=True,
        bgcolor=COLORS["paper_sunk"],
        padding=ft.Padding.symmetric(horizontal=14, vertical=9),
        border=ft.Border.only(bottom=ft.BorderSide(1, COLORS["card_border"])),
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    get_string("selected_count", count=count),
                    size=13.5,
                    font_family=FONT_SEMIBOLD,
                    color=COLORS["text_main"],
                ),
                ft.Container(width=6),
                btn(get_string("launch"), ft.Icons.PLAY_ARROW_ROUNDED, "launch", ACCENT_STYLE),
                btn(get_string("stop"), ft.Icons.STOP_ROUNDED, "stop", OUTLINE_STYLE),
                btn(get_string("delete"), ft.Icons.DELETE_OUTLINE, "delete", OUTLINE_STYLE),
                ft.Container(expand=True),
                ft.TextButton(
                    get_string("clear"),
                    on_click=lambda _: cbs["clear"](),
                    style=ft.ButtonStyle(color=COLORS["text_sub"]),
                ),
            ],
        ),
    )
