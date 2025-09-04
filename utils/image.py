"""Image utility helpers."""

from __future__ import annotations

import base64
import binascii


def decode_base64_image(data: str) -> bytes:
    """Return raw bytes from a base64-encoded image string.

    The ``data`` may include an optional ``data:*;base64,`` prefix which will
    be stripped automatically. A :class:`ValueError` is raised if the data is
    not valid base64.
    """

    if not isinstance(data, str) or not data:
        raise ValueError("Invalid base64 image data")
    # Remove any data URI scheme prefix
    data = data.split(",", 1)[-1]
    try:
        return base64.b64decode(data, validate=True)
    except (
        binascii.Error,
        ValueError,
    ) as exc:  # pragma: no cover - binascii raises Error
        raise ValueError("Invalid base64 image data") from exc
