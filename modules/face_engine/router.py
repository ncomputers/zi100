"""FastAPI routes exposing face engine capabilities."""

from __future__ import annotations

import functools
import time
import logging
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger

from config import config as cfg
from modules import face_db
from utils.image import decode_base64_image
from utils.license_guard import require_feature

from . import utils
from .detector import FaceDetector
from .embedder import FaceEmbedder

router = APIRouter(prefix="/face", tags=["face"])

detector: FaceDetector | None = None
embedder: FaceEmbedder | None = None


def _get_models() -> tuple[FaceDetector | None, FaceEmbedder | None]:
    """Lazily construct heavy face models when feature enabled."""
    global detector, embedder
    if not cfg.get("features", {}).get("face_recognition"):
        logger.info("Face recognition feature disabled; skipping model load")
        return None, None
    if detector is None:
        detector = FaceDetector()
    if embedder is None:
        embedder = FaceEmbedder(detector)
    return detector, embedder


def log_feature_disabled(message: str):
    """Decorator to log when a feature is disabled."""

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except HTTPException as exc:
                if exc.status_code == 403:
                    logger.warning(message)
                raise

        return wrapper

    return deco


logger = logging.getLogger(__name__)


# _read_image routine
async def _read_image(
    image: Optional[UploadFile], image_base64: Optional[str]
) -> bytes | None:
    """Read image data from upload or base64 string."""
    if image is not None:
        return await image.read()
    if image_base64:
        try:
            return decode_base64_image(image_base64)
        except ValueError:
            return None
    return None


@router.post("/upload")
@log_feature_disabled("Face recognition disabled; enable in settings or license")
@require_feature("face_recognition")
async def upload_face(
    image: UploadFile | None = File(None),
    image_base64: str | None = Form(None),
    name: str | None = Form(None),
):
    """Detect and store faces from an uploaded image."""
    detector, _ = _get_models()
    if detector is None:
        raise HTTPException(status_code=503, detail="models unavailable")
    try:
        data = await _read_image(image, image_base64)
    except IOError:
        logger.exception("Failed to read uploaded image")
        return JSONResponse({"error": "failed to read image"}, status_code=500)
    if not data:
        return JSONResponse({"error": "no image supplied"}, status_code=400)
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return JSONResponse({"error": "invalid image"}, status_code=400)
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    boxes = detector.detect_boxes(rgb)
    results = []
    for idx, bbox in enumerate(boxes):
        crop = utils.crop_face(arr, bbox)
        _, buf = cv2.imencode(".jpg", crop)
        face_id = name or f"face_{int(time.time()*1000)}_{idx}"
        ok, matches = face_db.insert(buf.tobytes(), face_id, source="upload")
        results.append(
            {"face_id": face_id, "bbox": bbox, "matches": matches, "inserted": ok}
        )
    return {"faces": results}


@router.post("/search")
@log_feature_disabled("Face recognition disabled; enable in settings or license")
@require_feature("face_recognition")
async def search_face(
    image: UploadFile = File(...),
    top_k: int = Form(1),
    threshold: float | None = Form(0.95),
):
    """Return best matches from the face database."""
    try:
        data = await image.read()
        matches = face_db.search_faces(data, top_k, threshold)
        return {"matches": matches}
    except HTTPException as exc:
        logger.warning("Face recognition disabled; enable in settings or license.")
        raise exc


@router.post("/verify")
@log_feature_disabled("Face recognition disabled; enable in settings or license")
@require_feature("face_recognition")
async def verify_face(image1: UploadFile = File(...), image2: UploadFile = File(...)):
    """Compare two face images and return cosine similarity."""
    _, embed = _get_models()
    if embed is None:
        raise HTTPException(status_code=503, detail="models unavailable")
    data1 = await image1.read()
    data2 = await image2.read()
    emb1 = embed.embed_bytes(data1)
    emb2 = embed.embed_bytes(data2)
    if not emb1 or not emb2:
        return {"score": 0.0}
    score = float(np.dot(emb1[0], emb2[0]))
    return {"score": score}


@router.post("/insert")
@log_feature_disabled("Face recognition disabled; enable in settings or license")
async def insert_face(
    person_id: str = Form(...),
    image: UploadFile = File(...),
    source: str = Form("upload"),
    merge_on_match: bool = Form(False),
    threshold: float = Form(0.95),
):
    """Insert a face image into the database without checks.

    The ``source`` parameter defaults to ``"upload"`` so that faces added
    through this endpoint are immediately registered as known.
    """
    try:
        data = await image.read()
        try:
            ok, matches = face_db.insert(
                data,
                person_id,
                source,
                merge_on_match=merge_on_match,
                threshold=threshold,
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if matches and not merge_on_match:
            return {"inserted": False, "matches": matches}
        if not ok:
            return JSONResponse({"error": "face insert failed"}, status_code=400)
        response = {"inserted": True}
        if matches:
            response["merged"] = True
            response["matches"] = matches
        return response
    except HTTPException as exc:
        logger.warning("Face recognition disabled; enable in settings or license.")
        raise exc
