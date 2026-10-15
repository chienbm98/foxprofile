"""The "Fingerprint" tab of the profile dialog: one row per fpsettings item.

Each row is a label plus a segmented control of the item's modes; "Custom" opens an
inline editor. `collect()` returns only the items that differ from what the profile
had (or from the defaults for a new profile), the shape the manager accepts.
"""

import contextlib
import os
from collections.abc import Callable
from typing import Any

import flet as ft

from ...core.config import DATA_DIR, HOST_OS
from ...core.strings import get_string
from ...models.profile import Profile
from ...services.browser import fingerprint, fpsettings
from ..theme.colors import COLORS, FONT_DATA, FONT_MEDIUM, FONT_SEMIBOLD
from ..theme.styles import DLG_FIELD_KWARGS, OUTLINE_STYLE

ORDER = (
    "os",
    "user_agent",
    "platform",
    "hardware_concurrency",
    "webgl_meta",
    "webgl_noise",
    "canvas",
    "audio",
    "webrtc",
    "timezone",
    "geo_permission",
    "geolocation",
    "language",
    "screen",
    "fonts",
    "media_devices",
    "voices",
    "port_scan",
)
PLATFORM = {"windows": "Win32", "macos": "MacIntel", "linux": "Linux x86_64"}
LANGUAGES = {"en-US": "English (en-US)", "zh-CN": "简体中文 (zh-CN)"}
HINT = {
    "os": "fp_hint_os",
    "webgl_noise": "fp_hint_noise",
    "canvas": "fp_hint_noise",
    "audio": "fp_hint_audio",
}
GROUPS = {
    "geolocation": (("latitude", "fp_lat"), ("longitude", "fp_lon"), ("accuracy", "fp_acc")),
    "media_devices": (
        ("micros", "fp_micros"),
        ("webcams", "fp_webcams"),
        ("speakers", "fp_speakers"),
    ),
}
_DATA = ft.TextStyle(font_family=FONT_DATA, size=13)
_SEGMENT_STYLE = ft.ButtonStyle(
    shape=ft.RoundedRectangleBorder(radius=7),
    side=ft.BorderSide(1, COLORS["rule_strong"]),
    bgcolor={
        ft.ControlState.SELECTED: COLORS["sidebar"],
        ft.ControlState.DEFAULT: COLORS["input_bg"],
    },
    color={
        ft.ControlState.SELECTED: COLORS["cover_ink"],
        ft.ControlState.DEFAULT: COLORS["text_sub"],
    },
    text_style=ft.TextStyle(font_family=FONT_MEDIUM, size=12.5),
    padding=ft.Padding.symmetric(horizontal=10),
)


def segmented(
    options: list[tuple[str, str]], value: str, on_change: Callable[[str], None]
) -> ft.SegmentedButton:
    """A one-of-N control in the dialog's tokens (selected = passport-cover green)."""
    return ft.SegmentedButton(
        segments=[ft.Segment(value=v, label=ft.Text(label)) for v, label in options],
        selected=[value],
        show_selected_icon=False,
        style=_SEGMENT_STYLE,
        on_change=lambda e: on_change(e.control.selected[0]) if e.control.selected else None,
    )


def _field(**kwargs: Any) -> ft.TextField:
    kwargs.setdefault("text_style", _DATA)
    return ft.TextField(**{**DLG_FIELD_KWARGS, **kwargs})


def _text(value: str, size: float = 12, color: str = COLORS["text_dim"], **kwargs: Any) -> ft.Text:
    return ft.Text(value, size=size, color=color, **kwargs)


class FingerprintPanel:
    def __init__(
        self,
        page: ft.Page,
        profile: Profile | None,
        os_type: str,
        engine: str,
        *,
        is_running: Callable[[], bool],
        proxy_set: Callable[[], bool],
    ) -> None:
        self.page = page
        self.profile = profile
        self.os_type = os_type
        self.engine = engine
        self.is_running = is_running
        self.proxy_set = proxy_set
        self.opts = fpsettings.options(os_type)
        self.settings: dict[str, dict] = {
            n: dict(s)
            for n, s in (profile.fingerprint if profile else fpsettings.defaults(os_type)).items()
        }
        self.base = {n: dict(s) for n, s in self.settings.items()}
        self.profile_dir = os.path.join(DATA_DIR, profile.name) if profile else ""
        self.rows = {n: ft.Container() for n in ORDER}
        self.editors: dict[str, Any] = {n: self._make_editor(n) for n in ORDER}
        self.warning_box = ft.Container(visible=False)
        self.device_box = ft.Column(spacing=4, tight=True)
        self.regen_row = ft.Row(spacing=8)
        self.chrome_note = ft.Container(
            visible=False,
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=8,
            bgcolor=COLORS["paper_sunk"],
            content=_text(get_string("fp_note_chrome"), 12.5, COLORS["text_sub"]),
        )
        self.body = ft.Column(
            spacing=0,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                self.device_box,
                self.regen_row,
                self.warning_box,
                ft.Column(spacing=0, controls=[self.rows[n] for n in ORDER]),
                ft.Container(
                    padding=ft.Padding.only(top=10),
                    content=_text(get_string("fp_next_launch")),
                ),
            ],
        )
        self.control = ft.Column(
            spacing=8,
            height=470,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[self.chrome_note, self.body],
        )
        for n in ORDER:
            self._render_row(n)
        self.refresh_device()
        self.set_engine(engine)

    # --- Values the dialog's other controls need ---------------------------------

    def custom_value(self, name: str) -> str:
        """The custom text of timezone / language, "" when that item is not custom."""
        if self.settings[name]["mode"] != "custom":
            return ""
        return (self.editors[name].value or "").strip()

    def use_language(self, value: str) -> None:
        self.settings["language"]["mode"] = "custom"
        self._set_language(value)
        self._render_row("language")

    def _set_language(self, value: str) -> None:
        # A stored or "Check IP"-suggested locale outside the list is kept as an extra option.
        choices = dict(LANGUAGES)
        choices.setdefault(value, value)
        self.language.options = [ft.dropdown.Option(k, v) for k, v in choices.items()]
        self.language.value = value

    def set_engine(self, engine: str) -> None:
        self.engine = engine
        chrome = engine == "chrome"
        self.chrome_note.visible = chrome
        self.body.visible = not chrome

    def set_os(self, os_type: str) -> None:
        """A new OS has its own GPUs, screens, fonts and platform string."""
        was_default = (self.editors["platform"].value or "") == PLATFORM[self.os_type]
        self.os_type = os_type
        self.opts = fpsettings.options(os_type)
        if was_default:
            self.editors["platform"].value = PLATFORM[os_type]
        gpu = self._gpu_selected()
        self._fill_gpus(gpu if gpu in self.opts["gpus"] else None)
        keep = (
            self.screen_text in self.opts["screens"] or self.settings["screen"]["mode"] == "custom"
        )
        self._fill_screens(self.screen_text if keep else None)
        for n in ("os", "webgl_meta", "screen", "platform", "fonts"):
            self._render_row(n)

    # --- Rows ------------------------------------------------------------------------

    def _render_row(self, name: str) -> None:
        cur = self.settings[name]
        modes = ["custom", "real"] if name == "os" else self.opts["items"][name]["modes"]
        hint = HINT.get(name) or (
            "fp_hint_geo_permission" if cur["mode"] == "prompt" and name == "geo_permission" else ""
        )
        editor = self._editor_view(name) if cur["mode"] == "custom" else None

        def change(mode: str, name: str = name) -> None:
            self.settings[name]["mode"] = mode
            self._render_row(name)
            self.page.update()

        self.rows[name].content = ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Row(
                    spacing=12,
                    wrap=True,
                    run_spacing=6,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            get_string(f"fp_item_{name}"),
                            size=13,
                            font_family=FONT_SEMIBOLD,
                            color=COLORS["text_sub"],
                        ),
                        segmented(
                            [(m, get_string(f"fp_mode_{m}")) for m in modes], cur["mode"], change
                        ),
                    ],
                ),
                *([_text(get_string(hint))] if hint else []),
                *([editor] if editor is not None else []),
            ],
        )
        self.rows[name].padding = ft.Padding.symmetric(vertical=9)
        self.rows[name].border = ft.Border(top=ft.BorderSide(1, COLORS["card_border"]))

    # --- Editors (created once so half-typed values survive mode switches) -------------

    def _make_editor(self, name: str) -> Any:
        value = self.settings[name]["value"]
        if name in ("user_agent", "webrtc", "timezone"):
            hints = {"webrtc": "203.0.113.7", "timezone": "Asia/Ho_Chi_Minh", "user_agent": ""}
            return _field(value=value or "", hint_text=hints[name])
        if name == "platform":
            return _field(value=value or PLATFORM[self.os_type], hint_text=PLATFORM[self.os_type])
        if name == "language":
            self.language = ft.Dropdown(
                text_size=13,
                bgcolor=COLORS["input_bg"],
                color=COLORS["text_main"],
                border_color=COLORS["rule_strong"],
                border_radius=8,
            )
            self._set_language(value or "en-US")
            return self.language
        if name == "hardware_concurrency":
            return _field(
                value=str(value or ""),
                keyboard_type=ft.KeyboardType.NUMBER,
                hint_text=str(self._device().get("hardware_concurrency") or 8),
            )
        if name == "webgl_meta":
            self.gpu = ft.Dropdown(
                text_size=13,
                bgcolor=COLORS["input_bg"],
                color=COLORS["text_main"],
                border_color=COLORS["rule_strong"],
                border_radius=8,
            )
            self._fill_gpus(value)
            return self.gpu
        if name == "screen":
            self.screen_text = value or ""
            self.screen = ft.Dropdown(
                editable=True,
                text_size=13,
                bgcolor=COLORS["input_bg"],
                color=COLORS["text_main"],
                border_color=COLORS["rule_strong"],
                border_radius=8,
                hint_text="1920x1080",
                on_select=lambda e: setattr(self, "screen_text", e.control.value or ""),
                on_text_change=lambda e: setattr(self, "screen_text", e.control.text or ""),
            )
            self._fill_screens(value)
            return self.screen
        if name == "fonts":
            return _field(value="\n".join(value or []), multiline=True, min_lines=5, max_lines=7)
        if name == "port_scan":
            return _field(
                value="\n".join(value or []),
                multiline=True,
                min_lines=2,
                max_lines=4,
                hint_text="localhost",
            )
        if name in GROUPS:
            defaults = {"accuracy": "50", "micros": "1", "webcams": "1", "speakers": "1"}
            given = value or {}
            return {
                key: _field(
                    label=get_string(label),
                    value=str(given.get(key, defaults.get(key, ""))),
                    keyboard_type=ft.KeyboardType.NUMBER,
                    expand=True,
                    label_style=ft.TextStyle(color=COLORS["text_sub"], size=12),
                )
                for key, label in GROUPS[name]
            }
        return None

    def _fill_gpus(self, current: dict | None = None) -> None:
        gpus = list(self.opts["gpus"])
        if current and current not in gpus:
            gpus.insert(0, current)
        self.gpus = gpus
        self.gpu.options = [
            ft.dropdown.Option(str(i), f"{g['vendor']} · {g['renderer']}")
            for i, g in enumerate(gpus)
        ]
        self.gpu.value = str(gpus.index(current)) if current in gpus else "0"

    def _gpu_selected(self) -> dict | None:
        if self.gpu.value is None or not self.gpu.value.isdigit():
            return None
        index = int(self.gpu.value)
        return self.gpus[index] if index < len(self.gpus) else None

    def _fill_screens(self, current: str | None = None) -> None:
        screens = self.opts["screens"]
        self.screen.options = [ft.dropdown.Option(s) for s in screens]
        self.screen_text = current or (screens[0] if screens else "")
        self.screen.value = self.screen_text

    def _editor_view(self, name: str) -> ft.Control | None:
        editor = self.editors[name]
        if editor is None:
            return None
        if name in GROUPS:
            return ft.Row(spacing=10, controls=list(editor.values()))
        if name == "fonts":
            return ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    editor,
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.OutlinedButton(
                                get_string("fp_fonts_fill"),
                                height=34,
                                style=OUTLINE_STYLE,
                                on_click=self._fill_fonts,
                            ),
                            _text(get_string("fp_hint_fonts")),
                        ],
                    ),
                ],
            )
        notes = {
            "screen": "fp_hint_screen",
            "port_scan": "fp_hint_port_scan",
        }
        if name in notes:
            return ft.Column(
                spacing=4, tight=True, controls=[editor, _text(get_string(notes[name]))]
            )
        return editor

    def _fill_fonts(self, _: ft.ControlEvent) -> None:
        self.editors["fonts"].value = "\n".join(self.opts["fonts"])
        self.page.update()

    # --- Device summary, warnings, regenerate ----------------------------------------------

    def _device(self) -> dict:
        return (fingerprint.summary(self.profile_dir) if self.profile_dir else None) or {}

    def refresh_device(self) -> None:
        if self.profile is None:
            self.device_box.controls = []
            self.regen_row.controls = []
            self.warning_box.visible = False
            return
        info = self._device()
        title = _text(
            get_string("fp_device_title"), 12.5, COLORS["text_sub"], font_family=FONT_SEMIBOLD
        )
        if info:
            pairs = (
                ("fp_platform", info.get("platform")),
                ("fp_screen", info.get("screen")),
                ("fp_cpu", info.get("hardware_concurrency")),
                ("fp_gpu", info.get("webgl_renderer")),
                ("fp_source", info.get("source")),
            )
            lines: list[ft.Control] = [
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(width=70, content=_text(get_string(k))),
                        ft.Text(
                            str(v or "?"),
                            size=12.5,
                            font_family=FONT_DATA,
                            color=COLORS["text_main"],
                            expand=True,
                            selectable=True,
                        ),
                    ],
                )
                for k, v in pairs
            ]
        else:
            lines = [_text(get_string("fp_device_none"))]
        self.device_box.controls = [
            title,
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                border_radius=8,
                bgcolor=COLORS["paper_sunk"],
                content=ft.Column(spacing=4, tight=True, controls=lines),
            ),
        ]
        self._render_regen()
        self._render_warnings()

    def _render_regen(self, confirm: bool = False) -> None:
        if self.profile is None or self.engine == "chrome":
            self.regen_row.controls = []
            return
        if self.is_running():
            self.regen_row.controls = [_text(get_string("fp_regen_stop"))]
        elif confirm:
            self.regen_row.controls = [
                _text(get_string("fp_regen_confirm"), 12, COLORS["warn_text"], expand=True),
                ft.TextButton(get_string("cancel"), on_click=lambda _: self._set_confirm(False)),
                ft.OutlinedButton(
                    get_string("fp_regen"),
                    height=34,
                    style=OUTLINE_STYLE,
                    on_click=self._regenerate,
                ),
            ]
        else:
            self.regen_row.controls = [
                ft.OutlinedButton(
                    get_string("fp_regen"),
                    icon=ft.Icons.AUTORENEW,
                    height=34,
                    style=OUTLINE_STYLE,
                    on_click=lambda _: self._set_confirm(True),
                )
            ]

    def _set_confirm(self, confirm: bool) -> None:
        self._render_regen(confirm)
        self.page.update()

    def _regenerate(self, _: ft.ControlEvent) -> None:
        if self.is_running():
            return self._set_confirm(False)
        fingerprint.reset(self.profile_dir)
        self.refresh_device()
        self.regen_row.controls = [_text(get_string("fp_regen_done"), 12, COLORS["success"])]
        self.page.update()

    def _render_warnings(self) -> None:
        warnings: list[str] = []
        if self.profile is not None and self.engine == "camoufox":
            with contextlib.suppress(Exception):
                device = fingerprint.load_saved(self.profile_dir)
                warnings = fpsettings.check(
                    self.settings,
                    device,
                    fpsettings.launch_os(self.settings, self.os_type),
                    HOST_OS,
                    self.proxy_set(),
                )
        self.warning_box.visible = bool(warnings)
        self.warning_box.padding = ft.Padding.symmetric(horizontal=12, vertical=10)
        self.warning_box.margin = ft.Margin.only(top=8)
        self.warning_box.border_radius = 8
        self.warning_box.bgcolor = COLORS["warn_tint"]
        self.warning_box.content = ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=16, color=COLORS["warning"]),
                        _text(
                            get_string("fp_warnings"),
                            12.5,
                            COLORS["warn_text"],
                            font_family=FONT_SEMIBOLD,
                        ),
                    ],
                ),
                *[_text(f"• {w}", 12, COLORS["warn_text"]) for w in warnings],
            ],
        )

    # --- Reading the form back ------------------------------------------------------------------

    def _number(self, name: str, raw: str | None) -> float:
        try:
            return float(str(raw).strip())
        except ValueError:
            raise ValueError(
                get_string("fp_bad_number", item=get_string(f"fp_item_{name}"))
            ) from None

    def _value(self, name: str) -> Any:
        editor = self.editors[name]
        if name == "webgl_meta":
            return self._gpu_selected()
        if name == "screen":
            return (self.screen_text or "").strip()
        if name in GROUPS:
            out = {k: self._number(name, f.value) for k, f in editor.items()}
            return out if name == "geolocation" else {k: int(v) for k, v in out.items()}
        text = (editor.value or "").strip()
        if name == "hardware_concurrency":
            return int(self._number(name, text))
        if name == "fonts":
            return [line.strip() for line in (editor.value or "").splitlines() if line.strip()]
        if name == "port_scan":
            return [h for h in (editor.value or "").replace(",", " ").split() if h]
        return text

    def collect(self, os_type: str) -> dict[str, dict]:
        """The items that differ from what was loaded; raises ValueError with a message."""
        if self.engine == "chrome":
            return {}
        out: dict[str, dict] = {}
        for name in ORDER:
            cur, was = self.settings[name], self.base[name]
            if cur["mode"] == "custom":
                value = os_type if name == "os" else self._value(name)
                if was["mode"] != "custom" or was["value"] != value:
                    out[name] = {"mode": "custom", "value": value}
            elif cur["mode"] != was["mode"]:
                out[name] = {"mode": cur["mode"]}
        return out
