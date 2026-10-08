import threading
import urllib.request

import flet as ft

from ...core.config import API_PORT, API_TOKEN
from ...core.strings import get_string
from ...services import mcp_setup
from ..theme.colors import COLORS
from ..theme.styles import ACCENT_STYLE, OUTLINE_STYLE

_API_URL = f"http://127.0.0.1:{API_PORT}"
_MCP_URL = f"{_API_URL}/mcp"


def _code_box(text: ft.Text) -> ft.Container:
    return ft.Container(
        content=text,
        bgcolor=COLORS["log_bg"],
        border=ft.Border.all(1, COLORS["card_border"]),
        border_radius=10,
        padding=14,
        width=620,
    )


def open_mcp_guide(page: ft.Page, clipboard: ft.Clipboard) -> None:
    """Step-by-step MCP setup with ready-to-paste configs for common AI apps."""
    state = {"client": "claude-code", "real_token": False}

    status = ft.Text(get_string("mcp_endpoint", url=_MCP_URL), size=12, color=COLORS["text_sub"])
    health = ft.Text("", size=12, color=COLORS["text_dim"])
    where = ft.Text("", size=13, weight=ft.FontWeight.BOLD, color=COLORS["text_main"])
    code = ft.Text("", size=12, font_family="Consolas", selectable=True, color=COLORS["text_main"])
    note = ft.Text("", size=12, color=COLORS["warning"], visible=False)
    copied = ft.Text("", size=12, color=COLORS["success"])
    client_row = ft.Row(spacing=8, wrap=True)
    example = ft.Text(
        get_string("mcp_example_prompt"),
        size=12,
        italic=True,
        selectable=True,
        color=COLORS["text_main"],
    )

    def configs() -> list[mcp_setup.ClientConfig]:
        token = None
        if API_TOKEN:
            token = API_TOKEN if state["real_token"] else mcp_setup.TOKEN_PLACEHOLDER
        return mcp_setup.build_configs(_MCP_URL, token, local=True, api_url=_API_URL)

    def render() -> None:
        all_configs = configs()
        current = next(c for c in all_configs if c.id == state["client"])
        client_row.controls = [
            (ft.Button if c.id == state["client"] else ft.OutlinedButton)(
                c.name,
                height=36,
                style=ACCENT_STYLE if c.id == state["client"] else OUTLINE_STYLE,
                on_click=lambda _, cid=c.id: select(cid),
            )
            for c in all_configs
        ]
        where.value = get_string("mcp_paste_into", where=current.where)
        code.value = current.code
        note.visible = current.id == "claude-desktop"
        note.value = get_string("mcp_desktop_note")
        copied.value = ""
        page.update()

    def select(client_id: str) -> None:
        state["client"] = client_id
        render()

    def toggle_token(e: ft.ControlEvent) -> None:
        state["real_token"] = bool(e.control.value)
        render()

    async def copy_code(_: ft.ControlEvent) -> None:
        await clipboard.set(code.value or "")
        copied.value = get_string("mcp_copied")
        page.update()

    async def copy_example(_: ft.ControlEvent) -> None:
        await clipboard.set(example.value or "")
        copied.value = get_string("mcp_copied")
        page.update()

    def check_health() -> None:
        try:
            with urllib.request.urlopen(f"{_API_URL}/api/v1/health", timeout=3):
                health.value = get_string("mcp_status_ok")
                health.color = COLORS["success"]
        except OSError as e:
            health.value = get_string("mcp_status_down", error=e)
            health.color = COLORS["error"]
        page.update()

    token_box = ft.Checkbox(
        label=get_string("mcp_show_token"),
        value=False,
        visible=bool(API_TOKEN),
        on_change=toggle_token,
    )

    dlg = ft.AlertDialog(
        modal=True,
        bgcolor=COLORS["card_bg"],
        title=ft.Row(
            spacing=10,
            controls=[
                ft.Icon(ft.Icons.SMART_TOY_OUTLINED, color=COLORS["accent"]),
                ft.Text(
                    get_string("mcp_title"),
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=COLORS["text_main"],
                ),
            ],
        ),
        content=ft.Container(
            width=640,
            content=ft.Column(
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text(get_string("mcp_intro"), size=13, color=COLORS["text_sub"]),
                    ft.Row(spacing=16, wrap=True, controls=[status, health]),
                    ft.Divider(height=10, color=COLORS["border"]),
                    ft.Text(
                        get_string("mcp_pick_client"),
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=COLORS["text_main"],
                    ),
                    client_row,
                    ft.Container(height=4),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        width=620,
                        controls=[
                            where,
                            ft.Button(
                                get_string("mcp_copy"),
                                icon=ft.Icons.CONTENT_COPY,
                                style=ACCENT_STYLE,
                                height=34,
                                on_click=copy_code,
                            ),
                        ],
                    ),
                    _code_box(code),
                    note,
                    token_box,
                    ft.Container(height=4),
                    ft.Text(
                        get_string("mcp_restart"),
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=COLORS["text_main"],
                    ),
                    ft.Row(
                        width=620,
                        controls=[
                            ft.Container(content=example, expand=True),
                            ft.IconButton(
                                icon=ft.Icons.CONTENT_COPY,
                                icon_size=16,
                                icon_color=COLORS["text_sub"],
                                tooltip=get_string("mcp_copy"),
                                on_click=copy_example,
                            ),
                        ],
                    ),
                    ft.Text(get_string("mcp_security_note"), size=11, color=COLORS["text_dim"]),
                    copied,
                ],
            ),
        ),
        actions=[
            ft.TextButton(
                get_string("close_btn"),
                style=ft.ButtonStyle(color=COLORS["text_sub"]),
                on_click=lambda _: page.pop_dialog(),
            ),
        ],
    )
    page.show_dialog(dlg)
    render()
    threading.Thread(target=check_health, daemon=True).start()
