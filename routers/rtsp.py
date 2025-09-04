from __future__ import annotations

import shutil
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter
from pydantic import BaseModel

from modules import stream_probe

router = APIRouter()


class ProbeRequest(BaseModel):
    url: str
    seconds: int = 6
    try_hw: bool = True


@router.post("/api/rtsp/probe")
async def rtsp_probe(req: ProbeRequest):
    if not (shutil.which("ffprobe") and shutil.which("ffmpeg")):
        return {"ok": False, "error": "ffmpeg/ffprobe not found"}

    parsed = urlparse(req.url)
    query_raw = parse_qs(parsed.query)
    query = {k: v[0] if len(v) == 1 else v for k, v in query_raw.items()}
    parsed_info = {
        "username": parsed.username,
        "host": parsed.hostname,
        "port": parsed.port,
        "path": parsed.path or "",
        "query": query,
    }

    try:
        summary = stream_probe.probe_stream(
            req.url, sample_seconds=req.seconds, enable_hwaccel=req.try_hw
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}

    meta = summary.get("metadata", {})
    meta_out = {
        "codec": meta.get("codec"),
        "profile": meta.get("profile"),
        "width": meta.get("width"),
        "height": meta.get("height"),
        "pix_fmt": meta.get("pix_fmt"),
        "bit_rate_bps": meta.get("bit_rate"),
        "avg_frame_rate_raw": meta.get("avg_frame_rate"),
        "r_frame_rate_raw": meta.get("r_frame_rate"),
        "nominal_fps": meta.get("nominal_fps"),
    }

    measure = {
        "effective_fps": summary.get("effective_fps"),
        "frames": summary.get("frames"),
        "elapsed_sec": summary.get("elapsed"),
        "transport_used": summary.get("transport"),
        "hwaccel_used": summary.get("hwaccel"),
    }

    return {"ok": True, "parsed": parsed_info, "meta": meta_out, "measure": measure}
