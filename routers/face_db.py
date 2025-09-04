from __future__ import annotations

"""Live face detection and recognition endpoints."""

import base64
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from config import config
from modules import face_db
from modules.camera_factory import open_capture
from utils.deps import get_cameras, get_templates
from utils.image import decode_base64_image

router = APIRouter()


@router.get("/face-db", response_class=HTMLResponse)
def face_db_page(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    """Render the simple Face DB webcam page."""
    cfg = getattr(request.app.state, "config", {})
    return templates.TemplateResponse("face_db.html", {"request": request, "cfg": cfg})


# init_context routine
def init_context(cfg: dict, redis_client) -> None:
    """Initialize required modules for face processing."""
    face_db.init(cfg, redis_client)


def open_and_capture(cam: dict) -> np.ndarray:
    """Open a camera and capture a single frame.

    Parameters
    ----------
    cam: dict
        Camera configuration dictionary.

    Returns
    -------
    np.ndarray
        Captured BGR frame.

    Raises
    ------
    HTTPException
        If the camera cannot be opened or no frame is returned.
    """

    src = cam.get("url") or cam.get("src")
    cam_id = cam.get("id")
    src_type = cam.get("type") or cam.get("src_type", "http")
    resolution = cam.get("resolution", "original")
    rtsp_transport = cam.get("rtsp_transport", "tcp")
    stream_mode = cam.get("stream_mode", "gstreamer")
    use_gpu = cam.get("use_gpu", True)
    capture_buffer = cam.get("capture_buffer", 3)
    local_buffer_size = cam.get("local_buffer_size", 1)
    backend = cam.get("backend")
    try:
        cap, _ = open_capture(
            src,
            cam_id,
            src_type,
            resolution,
            rtsp_transport,
            stream_mode,
            use_gpu,
            capture_buffer,
            local_buffer_size,
            backend_priority=backend,
            ready_frames=cam.get("ready_frames"),
            ready_timeout=cam.get("ready_timeout"),
        )
    except Exception as exc:  # pragma: no cover - capture failure
        raise HTTPException(status_code=500, detail="Camera open failed") from exc

    try:
        ret, frame = cap.read()
    finally:
        cap.release()

    if not ret or frame is None:
        raise HTTPException(status_code=500, detail="Failed to read frame")
    return frame


def match_faces(rgb_frame: np.ndarray, threshold: float) -> list[dict[str, Any]]:
    """Run face matching on an RGB frame."""

    results: list[dict[str, Any]] = []
    if face_db.face_app is None:
        return results
    faces = face_db.face_app.get(rgb_frame)
    for f in faces:
        x1, y1, x2, y2 = [int(v) for v in getattr(f, "bbox", [0, 0, 0, 0])]
        emb = getattr(f, "embedding", None)
        name = "unknown"
        fid = None
        confidence = 0.0
        gate_pass_id = ""
        visitor_type = ""
        if (
            emb is not None
            and face_db.faiss_index is not None
            and face_db.faiss_index.ntotal > 0
        ):
            vec = np.array(emb, dtype=np.float32)
            if np.any(vec):
                vec /= max(np.linalg.norm(vec), 1e-6)
                D, I = face_db.faiss_index.search(vec.reshape(1, -1), 1)
                confidence = float(D[0][0])
                if confidence >= threshold:
                    idx = int(I[0][0])
                    if 0 <= idx < len(face_db.id_map):
                        fid = face_db.id_map[idx].split(":", 1)[-1]
                        if face_db.redis_client:
                            rec = face_db.redis_client.hgetall(f"face:known:{fid}")
                            face_db.redis_client.hset(
                                f"face:known:{fid}", "confidence", str(confidence)
                            )
                            if rec:
                                fields: dict[str, Any] = {}
                                for k, v in rec.items():
                                    key = k.decode() if isinstance(k, bytes) else k
                                    val = v.decode() if isinstance(v, bytes) else v
                                    fields[key] = val
                                name = fields.get("name", fid)
                                gate_pass_id = fields.get("gate_pass_id", "")
                                visitor_type = fields.get("visitor_type", "")
                            else:
                                name = fid
        results.append(
            {
                "box": [x1, y1, x2 - x1, y2 - y1],
                "name": name,
                "id": fid,
                "confidence": confidence,
                "gate_pass_id": gate_pass_id,
                "visitor_type": visitor_type,
            }
        )
    return results


@router.post("/face_quality")
async def face_quality(payload: dict = Body(...)):
    """Evaluate pose, blur, and brightness of the first detected face."""
    img_b64 = payload.get("image")
    if not img_b64:
        raise HTTPException(status_code=400, detail="Image required")
    try:
        data = decode_base64_image(img_b64)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid image data") from exc
    if face_db.face_app is None:
        raise HTTPException(status_code=503, detail="face model unavailable")
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise HTTPException(status_code=400, detail="Image decode failed")
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    faces = face_db.face_app.get(rgb)
    if not faces:
        return JSONResponse({"error": "no_face"}, status_code=400)
    f = faces[0]
    x1, y1, x2, y2 = [int(v) for v in getattr(f, "bbox", [0, 0, 0, 0])]
    crop = arr[y1:y2, x1:x2].copy()
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    pose_vals = getattr(f, "pose", [0.0, 0.0, 0.0])
    pitch, yaw, roll = (float(v) for v in pose_vals[:3])
    pose = {"pitch": pitch, "yaw": yaw, "roll": roll}
    blur_score = min(1.0, blur / 100.0)
    bright_score = 1 - min(1.0, abs(brightness - 128) / 128)
    pose_pen = min(1.0, (abs(pitch) + abs(yaw) + abs(roll)) / 90.0)
    pose_score = max(0.0, 1.0 - pose_pen)
    quality = (blur_score + bright_score + pose_score) / 3.0
    return {
        "pose": pose,
        "blur": blur,
        "brightness": brightness,
        "quality": quality,
    }


@router.post("/process_frame")
async def process_frame(
    payload: dict = Body(...),
    scaleFactor: float | None = Query(None),
    minNeighbors: int | None = Query(None),
    threshold: float | None = Query(None),
    minFaceSize: int | None = Query(None),
):
    """Detect and identify faces in a base64 encoded frame.

    Parameters
    ----------
    payload: dict
        Expected keys are ``image`` (base64 JPEG), ``scaleFactor`` and
        ``minNeighbors``.
    """
    if not config.get("enable_face_recognition", True):
        raise HTTPException(status_code=403, detail="Face recognition disabled")
    try:
        img_b64 = payload["image"]
        scale = float(
            payload.get("scaleFactor", scaleFactor if scaleFactor is not None else 1.1)
        )
        neighbors = int(
            payload.get("minNeighbors", minNeighbors if minNeighbors is not None else 5)
        )
        size = int(
            payload.get("minFaceSize", minFaceSize if minFaceSize is not None else 60)
        )
        threshold = float(
            payload.get(
                "threshold",
                (
                    threshold
                    if threshold is not None
                    else config.get("face_match_thresh", 0.6)
                ),
            )
        )
    except Exception as exc:  # pragma: no cover - invalid types
        raise HTTPException(status_code=400, detail="Invalid payload") from exc

    if (
        not (0.5 <= scale <= 1.5)
        or not (1 <= neighbors <= 10)
        or not (20 <= size <= 200)
    ):
        raise HTTPException(status_code=400, detail="Invalid detection parameters")

    try:
        data = decode_base64_image(img_b64)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid image data") from exc
    if face_db.face_app is None:
        return {"faces": []}

    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise HTTPException(status_code=400, detail="Image decode failed")
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    results = match_faces(rgb, threshold)
    return JSONResponse({"faces": results})


@router.get("/process_camera/{cam_id}")
async def process_camera(
    cam_id: int,
    scaleFactor: float | None = Query(None),
    minNeighbors: int | None = Query(None),
    threshold: float | None = Query(None),
    minFaceSize: int | None = Query(None),
    cams: list = Depends(get_cameras),
):
    """Capture a frame from the given camera and run face recognition."""
    if not config.get("enable_face_recognition", True):
        raise HTTPException(status_code=403, detail="Face recognition disabled")
    cam = next((c for c in cams if c.get("id") == cam_id), None)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    scale = float(scaleFactor if scaleFactor is not None else 1.1)
    neighbors = int(minNeighbors if minNeighbors is not None else 5)
    size = int(minFaceSize if minFaceSize is not None else 60)
    if (
        not (0.5 <= scale <= 1.5)
        or not (1 <= neighbors <= 10)
        or not (20 <= size <= 200)
    ):
        raise HTTPException(status_code=400, detail="Invalid detection parameters")

    frame = open_and_capture(cam)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    thresh = float(
        threshold if threshold is not None else config.get("face_match_thresh", 0.6)
    )
    results = match_faces(rgb, thresh)
    _, jpg = cv2.imencode(".jpg", frame)
    img_b64 = base64.b64encode(jpg.tobytes()).decode()
    return JSONResponse({"image": img_b64, "faces": results})
