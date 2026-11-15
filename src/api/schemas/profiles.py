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
        description="camoufox (Firefox) or chrome (Chromium, fingerprint-chromium). "
        "Fixed once the profile is created",
    )
    extension: str | None = Field(
        None,
        description="Deprecated alias for proxy_mode=proton; the extension follows proxy_mode",
    )
    proxy_mode: str | None = Field(
        None,
        description="direct, proxy or proton. Unset = infer from proxy/extension",
    )
    proton_user: str | None = Field(None, description="Proton username for proton mode")
    proton_password: str | None = Field(
        None, description="Proton password for proton mode; never returned"
    )
    proton_totp: str | None = Field(None, description="Base32 TOTP secret or otpauth:// URI")
    proton_country: str | None = Field(
        None, description="Proton exit country ISO code, e.g. US; empty = Quick Connect"
    )


class ProfileUpdate(BaseModel):
    """All fields optional — only supplied fields are changed."""

    name: str | None = None
    proxy: str | None = None
    os_type: str | None = None
    timezone: str | None = Field(None, description='"" switches back to automatic')
    locale: str | None = Field(None, description='"" switches back to automatic')
    engine: str | None = Field(None, description="Cannot be changed; only the current value")
    proxy_mode: str | None = Field(None, description="direct, proxy or proton")
    proton_user: str | None = Field(None, description="Proton username for proton mode")
    proton_password: str | None = Field(None, description="Omit to keep the saved password")
    proton_totp: str | None = Field(None, description="Omit to keep the saved secret")
    proton_country: str | None = Field(None, description="Proton exit country ISO code")


class ProfileResponse(BaseModel):
    name: str
    proxy: str | None
    os_type: str
    timezone: str | None = None
    locale: str | None = None
    engine: str = "camoufox"
    extension: str | None = None
    proxy_mode: str = "direct"
    proton_user: str = ""
    has_proton_password: bool = False
    proton_totp_set: bool = False
    proton_country: str = ""
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
