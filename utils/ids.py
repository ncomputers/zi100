from __future__ import annotations

import uuid


def generate_id() -> str:
    """Return a random 32-character hexadecimal string."""
    return uuid.uuid4().hex
