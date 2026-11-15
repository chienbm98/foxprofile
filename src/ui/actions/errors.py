"""The message the user sees when a profile operation is refused or fails."""

from ...core.errors import ProfileBusyError
from ...core.strings import get_string


def failure_message(name: str, error: Exception) -> str:
    if isinstance(error, ProfileBusyError):
        return get_string("busy_profile", name=name)
    return str(error)
