"""Proton VPN reference data for the profile form."""

from fastapi import APIRouter

from ...services.browser.proton_countries import COUNTRIES
from ..schemas.proton import ProtonCountry

router = APIRouter(prefix="/proton", tags=["proton"])


@router.get("/countries", response_model=list[ProtonCountry])
def list_countries() -> list[ProtonCountry]:
    """Countries where Proton VPN has servers (ISO code + English name)."""
    return [ProtonCountry(code=code, name=name) for code, name in COUNTRIES]
