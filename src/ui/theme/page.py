import os

import flet as ft

from ...core.strings import get_string
from .colors import COLORS, FONT, FONT_BOLD, FONT_DATA, FONT_MEDIUM, FONT_SEMIBOLD


def build_page_theme() -> ft.Theme:
    return ft.Theme(
        font_family=FONT,
        color_scheme_seed=COLORS["sidebar"],
        color_scheme=ft.ColorScheme(
            primary=COLORS["sidebar"],
            on_primary="#FFFFFF",
            secondary=COLORS["accent"],
            surface=COLORS["card_bg"],
            on_surface=COLORS["text_main"],
            on_surface_variant=COLORS["text_sub"],
            surface_container=COLORS["bg"],
            surface_container_high=COLORS["card_bg"],
            outline=COLORS["rule_strong"],
            outline_variant=COLORS["card_border"],
            error=COLORS["error"],
        ),
        scrollbar_theme=ft.ScrollbarTheme(
            thumb_color=COLORS["scrollbar_grab"],
            thickness=8,
            radius=8,
        ),
        tooltip_theme=ft.TooltipTheme(
            decoration=ft.BoxDecoration(bgcolor=COLORS["text_main"], border_radius=6),
            text_style=ft.TextStyle(color="#F2F4F1", size=12),
        ),
        checkbox_theme=ft.CheckboxTheme(
            fill_color={ft.ControlState.SELECTED: COLORS["sidebar"]},
            border_side=ft.BorderSide(1.5, COLORS["text_sub"]),
            shape=ft.RoundedRectangleBorder(radius=4),
        ),
    )


_FONT_FILES = {
    FONT: "fonts/BeVietnamPro-Regular.ttf",
    FONT_MEDIUM: "fonts/BeVietnamPro-Medium.ttf",
    FONT_SEMIBOLD: "fonts/BeVietnamPro-SemiBold.ttf",
    FONT_BOLD: "fonts/BeVietnamPro-Bold.ttf",
    FONT_DATA: "fonts/JetBrainsMono.ttf",
}

ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets"))


def build_os_dropdown(value: str = "windows") -> ft.Dropdown:
    return ft.Dropdown(
        label=get_string("operating_system"),
        value=value,
        bgcolor=COLORS["input_bg"],
        color=COLORS["text_main"],
        border_color=COLORS["rule_strong"],
        focused_border_color=COLORS["sidebar"],
        label_style=ft.TextStyle(color=COLORS["text_sub"]),
        border_radius=8,
        options=[
            ft.dropdown.Option("windows", "Windows"),
            ft.dropdown.Option("macos", "macOS"),
            ft.dropdown.Option("linux", "Linux"),
        ],
    )


def build_engine_dropdown(value: str = "camoufox", disabled: bool = False) -> ft.Dropdown:
    return ft.Dropdown(
        label=get_string("browser_engine"),
        value=value,
        disabled=disabled,
        bgcolor=COLORS["input_bg"],
        color=COLORS["text_main"],
        border_color=COLORS["rule_strong"],
        focused_border_color=COLORS["sidebar"],
        label_style=ft.TextStyle(color=COLORS["text_sub"]),
        border_radius=8,
        options=[
            ft.dropdown.Option("camoufox", get_string("engine_camoufox")),
            ft.dropdown.Option("chrome", get_string("engine_chrome")),
        ],
    )


def configure_page(page: ft.Page) -> None:
    page.title = get_string("window_title")
    page.window.width, page.window.height = 1400, 860
    page.window.min_width, page.window.min_height = 1180, 680

    icon_name = "icon.ico" if os.name == "nt" else "icon.png"
    icon_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "assets", icon_name)
    )
    if os.path.exists(icon_path):
        page.window.icon = icon_path

    page.padding = page.spacing = 0
    page.fonts = dict(_FONT_FILES)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = COLORS["bg"]
    page.theme = build_page_theme()
