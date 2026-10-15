from pydantic import BaseModel, Field

from ...core.config import DEFAULT_ENGINE, HOST_OS


class ProfileCreate(BaseModel):
    name: str
    proxy: str | None = None
    os_type: str = HOST_OS
    timezone: str | None = Field(
        None, description="IANA timezone, e.g. Asia/Ho_Chi_Minh. Unset = follow the IP"
    )
    locale: str | None = Field(
        None, description="language-REGION, e.g. vi-VN. Unset = follow the IP"
    )
    engine: str = Field(
        DEFAULT_ENGINE,
        description="camoufox (Firefox, default) or chrome (fingerprint-chromium). "
        "Fixed once the profile is created",
    )
    fingerprint: dict | None = Field(
        None,
        description='Fingerprint settings {item: {"mode": ..., "value": ...}}; see /fingerprint/options',
    )


class ProfileUpdate(BaseModel):
    """All fields optional — only supplied fields are changed."""

    name: str | None = None
    proxy: str | None = None
    os_type: str | None = None
    timezone: str | None = Field(None, description='"" switches back to automatic')
    locale: str | None = Field(None, description='"" switches back to automatic')
    engine: str | None = Field(None, description="Cannot be changed; only the current value")
    fingerprint: dict | None = Field(
        None, description="Fingerprint settings items to change; the others are kept"
    )


class ProfileResponse(BaseModel):
    name: str
    proxy: str | None
    os_type: str
    timezone: str | None = None
    locale: str | None = None
    engine: str = "camoufox"
    data_dir: str
    is_running: bool


class ProfileListResponse(BaseModel):
    profiles: list[ProfileResponse]
    total: int


class DataDirResponse(BaseModel):
    name: str
    data_dir: str
    exists: bool


class ExportRequest(BaseModel):
    export_dir: str
    include_data: bool = True


class ExportResponse(BaseModel):
    success: bool
    zip_path: str | None = None
    error: str | None = None


class ImportRequest(BaseModel):
    zip_path: str
    overwrite: bool = False


class ImportResponse(BaseModel):
    success: bool
    profile_name: str | None = None
    error: str | None = None


class CookieImportRequest(BaseModel):
    """Cookies as JSON (Cookie-Editor / EditThisCookie / Playwright) or Netscape text."""

    content: str


class CookieImportResponse(BaseModel):
    success: bool
    imported: int = 0
    error: str | None = None


class FingerprintResponse(BaseModel):
    name: str
    exists: bool
    os: str | None = None
    platform: str | None = None
    screen: str | None = None
    hardware_concurrency: int | None = None
    webgl_renderer: str | None = None
    source: str | None = None
    settings: dict | None = None
    warnings: list[str] = []


class FingerprintSettingsResponse(BaseModel):
    name: str
    settings: dict
    warnings: list[str]
    applies_on_next_launch: bool = Field(
        description="True while the browser is running: it keeps the old settings until relaunched"
    )
