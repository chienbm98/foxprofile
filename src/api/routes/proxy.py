from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from ...services.proxy.geo_check import check_geo
from ...utils.validation import validate_locale, validate_proxy_format, validate_timezone
from ..dependencies import get_proxy_service
from ..schemas.proxy import GeoCheckRequest, GeoCheckResponse, ProxyCheckRequest, ProxyCheckResponse

if TYPE_CHECKING:
    from ...interfaces import IProxyService

router = APIRouter(prefix="/proxy", tags=["proxy"])


@router.post("/check", response_model=ProxyCheckResponse)
def check_proxy(
    body: ProxyCheckRequest,
    ps: IProxyService = Depends(get_proxy_service),
) -> ProxyCheckResponse:
    ok, message = ps.check_proxy_sync(body.proxy, body.timeout or 10)
    return ProxyCheckResponse(success=ok, message=message)


@router.post("/geo-check", response_model=GeoCheckResponse)
def geo_check(body: GeoCheckRequest) -> GeoCheckResponse:
    """Check an unsaved proxy / timezone / locale combination (see GET /profiles/{name}/ip-check)."""
    for validate, value in (
        (validate_proxy_format, body.proxy),
        (validate_timezone, body.timezone),
        (validate_locale, body.locale),
    ):
        valid, msg = validate(value or "")
        if not valid:
            raise HTTPException(status_code=400, detail=msg)
    return GeoCheckResponse.from_result(
        check_geo(body.proxy or None, body.timezone or None, body.locale or None)
    )
