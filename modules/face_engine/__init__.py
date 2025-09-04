"""Face recognition engine module.

This package provides detector, embedder, utilities, and API routes
for handling face images from various sources (uploads, webcam, RTSP).
"""

from .detector import FaceDetector
from .embedder import FaceEmbedder

__all__ = ["FaceDetector", "FaceEmbedder"]
