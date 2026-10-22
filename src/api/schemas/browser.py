from pydantic import BaseModel


class BrowserStatusResponse(BaseModel):
    name: str
    is_running: bool


class RunningBrowsersResponse(BaseModel):
    running: list[str]
    # Progress of browsers still starting, e.g. a first-run browser download.
    starting: dict[str, str] = {}
    count: int


class LaunchResponse(BaseModel):
    success: bool
    message: str
