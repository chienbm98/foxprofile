from typing import Literal

from pydantic import BaseModel, Field


class NavigateRequest(BaseModel):
    url: str
    wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = "load"


class ClickRequest(BaseModel):
    selector: str = Field(
        description="Playwright selector: CSS, text=..., or role=button[name='...']"
    )
    timeout: int = Field(10_000, ge=100, le=120_000)


class TypeRequest(BaseModel):
    selector: str
    text: str = Field(max_length=20_000)
    submit: bool = Field(False, description="Press Enter after typing")
    clear: bool = Field(True, description="Replace the field's value instead of appending")
    timeout: int = Field(10_000, ge=100, le=120_000)


class PressRequest(BaseModel):
    key: str = Field(description="Key name such as Enter, Tab, Escape, Control+A")
    selector: str | None = None


class ClickAtRequest(BaseModel):
    x: float = Field(ge=0, description="Viewport X in CSS pixels, as on a screenshot")
    y: float = Field(ge=0, description="Viewport Y in CSS pixels, as on a screenshot")


class KeyboardTypeRequest(BaseModel):
    text: str = Field(max_length=20_000)


class WaitRequest(BaseModel):
    selector: str
    timeout: int = Field(15_000, ge=100, le=120_000)


class EvaluateRequest(BaseModel):
    script: str = Field(
        max_length=200_000,
        description="JavaScript expression or function body, e.g. document.title",
    )


class TabNewRequest(BaseModel):
    url: str | None = None


class UploadRequest(BaseModel):
    selector: str = Field(
        description="File input to fill, e.g. input[type=file]; hidden inputs work"
    )
    paths: list[str] = Field(
        min_length=1,
        max_length=10,
        description="Files inside the upload directory (TQD_UPLOAD_DIR, default media_outbox)",
    )
    timeout: int = Field(15_000, ge=100, le=120_000)


class WaitUrlRequest(BaseModel):
    pattern: str = Field(description="Text the URL must contain, e.g. /checkpoint or /me")
    timeout: int = Field(15_000, ge=100, le=120_000)


class WaitTextRequest(BaseModel):
    text: str = Field(max_length=500)
    timeout: int = Field(15_000, ge=100, le=120_000)


class ScrollRequest(BaseModel):
    dy: int = Field(600, ge=-20_000, le=20_000, description="Pixels to scroll down (negative: up)")
    to: Literal["top", "bottom"] | None = Field(
        None, description="Jump to the top or bottom instead"
    )
