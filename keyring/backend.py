class KeyringBackend:
    """Minimal keyring backend interface for tests."""
    priority = 0

    def get_password(self, service, username):  # pragma: no cover - interface
        raise NotImplementedError

    def set_password(self, service, username, password):  # pragma: no cover - interface
        raise NotImplementedError

    def delete_password(self, service, username):  # pragma: no cover - interface
        raise NotImplementedError
