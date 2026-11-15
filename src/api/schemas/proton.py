from pydantic import BaseModel


class ProtonCountry(BaseModel):
    code: str
    name: str
