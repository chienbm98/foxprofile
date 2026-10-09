import flet as ft

from ...core.strings import get_string
from ..theme.colors import COLORS, FONT_BOLD


def build_content_area(
    subtitle: ft.Text,
    profile_list: ft.Column,
    prev_btn: ft.IconButton,
    next_btn: ft.IconButton,
    page_label: ft.Text,
    bulk_bar: ft.Control | None = None,
    search_field: ft.Control | None = None,
    header_slot: ft.Container | None = None,
) -> ft.Container:
    """Main content: title, search, then the profile sheet (bulk bar, header, rows)."""
    sheet = ft.Container(
        expand=True,
        bgcolor=COLORS["card_bg"],
        border=ft.Border.all(1, COLORS["card_border"]),
        border_radius=10,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Column(
            spacing=0,
            expand=True,
            controls=[
                *([] if bulk_bar is None else [bulk_bar]),
                *([] if header_slot is None else [header_slot]),
                profile_list,
            ],
        ),
    )
    return ft.Container(
        expand=True,
        bgcolor=COLORS["bg"],
        padding=ft.Padding.only(left=32, right=32, top=26, bottom=16),
        content=ft.Column(
            spacing=0,
            expand=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Column(
                            spacing=2,
                            controls=[
                                ft.Text(
                                    get_string("your_profiles"),
                                    size=26,
                                    font_family=FONT_BOLD,
                                    color=COLORS["text_main"],
                                ),
                                subtitle,
                            ],
                        ),
                        *([] if search_field is None else [search_field]),
                    ],
                ),
                ft.Container(height=18),
                sheet,
                ft.Container(height=10),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[prev_btn, page_label, next_btn],
                ),
            ],
        ),
    )
