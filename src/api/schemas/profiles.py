from pydantic import BaseModel, Field


class ProfileCreate(BaseModel):
    name: str
    proxy: str | None = None
    os_type: str = "windows"
    timezone: str | None = Field(
        None, description="IANA timezone, e.g. Asia/Ho_Chi_Minh. Unset = follow the IP"
    )
    locale: str | None = Field(
        None, description="language-REGION, e.g. vi-VN. Unset = follow the IP"
    )
    engine: str = Field(
        "camoufox",
        description="camoufox (Firefox) or chrome (experimental, fingerprint-chromium). "
        "Fixed once the profile is created",
    )
    email: str | None = Field(None, description="Account address this profile is logged in as")
    purpose: str | None = Field(None, description="What the profile is for, e.g. free signups")
    notes: str | None = Field(None, description="Free-form multi-line notes")
    tags: list[str] | None = Field(None, description="Labels for filtering, e.g. gmail, free")
    login_mode: str | None = Field(None, description="full, email_only or manual")
    auto_login: bool | None = Field(None, description="Sign back in by itself when logged out")


class ProfileUpdate(BaseModel):
    """All fields optional — only supplied fields are changed."""

    name: str | None = None
    proxy: str | None = None
    os_type: str | None = None
    timezone: str | None = Field(None, description='"" switches back to automatic')
    locale: str | None = Field(None, description='"" switches back to automatic')
    engine: str | None = Field(None, description="Cannot be changed; only the current value")
    email: str | None = Field(None, description="Account address this profile is logged in as")
    purpose: str | None = Field(None, description="What the profile is for, e.g. free signups")
    notes: str | None = Field(None, description="Free-form multi-line notes")
    tags: list[str] | None = Field(None, description="Labels for filtering, e.g. gmail, free")
    login_mode: str | None = Field(None, description="full, email_only or manual")
    auto_login: bool | None = Field(None, description="Sign back in by itself when logged out")


class ProfileResponse(BaseModel):
    name: str
    proxy: str | None
    os_type: str
    timezone: str | None = None
    locale: str | None = None
    engine: str = "camoufox"
    data_dir: str
    is_running: bool
    email: str | None = None
    purpose: str | None = None
    notes: str | None = None
    tags: list[str] = []
    session_state: str | None = None
    session_checked_at: float | None = None
    # Only filled in by the list endpoint, so the panel needs no request per profile.
    fingerprint: dict | None = None
    login_mode: str = "full"
    auto_login: bool = False
    # Which secrets are stored; their values are never part of this response.
    has_password: bool = False
    has_totp_secret: bool = False
    has_backup_codes: bool = False
    has_recovery: bool = False
    has_hint: bool = False


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
