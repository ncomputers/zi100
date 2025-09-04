"""Utilities for creating video capture streams."""

from .camera_factory import StreamUnavailable, open_capture

__all__ = ["open_capture", "StreamUnavailable"]
