"""The message the user sees when a profile operation is refused or fails."""

from ...core.errors import ProfileAccountSaveError, ProfileBusyError, ProfileStoreError
from ...core.strings import get_string


def failure_message(name: str, error: Exception) -> str:
    """What the user reads. The technical detail is in the log, not in the dialog."""
    if isinstance(error, ProfileBusyError):
        return get_string("busy_profile", name=name)
    if isinstance(error, ProfileAccountSaveError):
        return get_string("profile_saved_account_failed")
    if isinstance(error, ProfileStoreError):
        return get_string("profile_store_failed")
    return str(error)
