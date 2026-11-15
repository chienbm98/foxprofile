"""Errors the service layer raises. The API and the desktop app turn them into messages."""


class ProfileBusyError(Exception):
    """The profile's browser is running, or another operation holds its data directory."""


class ProfileStoreError(RuntimeError):
    """A profile change could not be saved. The in-memory state was rolled back."""


class ProtonStoreError(RuntimeError):
    """The Proton account store cannot be read or decrypted. Nothing has been overwritten."""
