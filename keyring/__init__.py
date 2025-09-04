"""Minimal stub of the ``keyring`` package used in tests.

This provides just enough functionality for the test suite without requiring
external dependencies."""

from .backend import KeyringBackend

_backend = None


def set_keyring(backend: KeyringBackend) -> None:
    """Set the active keyring backend."""
    global _backend
    _backend = backend


def get_keyring() -> KeyringBackend | None:
    """Return the currently configured backend."""
    return _backend


def get_password(service: str, username: str):
    if _backend is None:
        return None
    return _backend.get_password(service, username)


def set_password(service: str, username: str, password: str) -> None:
    if _backend is None:
        raise RuntimeError("No keyring backend set")
    _backend.set_password(service, username, password)


def delete_password(service: str, username: str) -> None:
    if _backend is None:
        raise RuntimeError("No keyring backend set")
    _backend.delete_password(service, username)
