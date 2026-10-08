from __future__ import annotations

from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field

from ...services.proxy.geo_check import GeoCheckResult


class ProxyCheckRequest(BaseModel):
    proxy: str
    timeout: int | None = None


class ProxyCheckResponse(BaseModel):
    success: bool
    message: str


class GeoCheckRequest(BaseModel):
    proxy: str | None = None
    timezone: str | None = None
    locale: str | None = None


class GeoSource(BaseModel):
    source: str
    ip: str | None = None
    country: str | None = None
    city: str | None = None
    timezone: str | None = None
    hosting: bool | None = None
    error: str | None = None


class GeoWarningItem(BaseModel):
    code: str
    params: dict[str, Any]
    message: str


class GeoCheckResponse(BaseModel):
    exit_ip: str | None = Field(description="Exit IP as Camoufox resolves it at launch")
    country: str | None = Field(description="Country of the exit IP in Camoufox's GeoIP database")
    auto_timezone: str | None
    suggested_locale: str | None = Field(description="Most spoken locale of the country")
    timezone: str | None = Field(description="Timezone the browser will present")
    timezone_pinned: bool
    locale: str | None = Field(description="Pinned locale; null = random per launch")
    locale_pinned: bool
    sources: list[GeoSource]
    warnings: list[GeoWarningItem]
    error: str | None = None

    @classmethod
    def from_result(cls, r: GeoCheckResult) -> GeoCheckResponse:
        data = asdict(r)
        data["warnings"] = [
            {"code": w.code, "params": w.params, "message": w.message} for w in r.warnings
        ]
        return cls(**data)
