"""Routes for submitting user feedback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from modules import feedback_db
from utils.deps import get_redis, get_settings, get_templates
from utils.ids import generate_id

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "feedback"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/feedback", response_class=HTMLResponse)
async def feedback_page(
    request: Request,
    cfg: dict = Depends(get_settings),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Render the feedback submission form."""
    return templates.TemplateResponse("feedback.html", {"request": request, "cfg": cfg})


@router.get("/feedback/recent")
async def recent_feedback(limit: int = 5, redis=Depends(get_redis)) -> List[dict]:
    """Return the most recent feedback entries."""
    entries = feedback_db.list_feedback(redis)
    return list(reversed(entries[-limit:]))


@router.post("/feedback")
async def submit_feedback(
    title: str = Form(...),
    type: str = Form(...),
    severity: str = Form(...),
    module: str = Form(...),
    description: str = Form(...),
    expected: str = Form(""),
    actual: str = Form(""),
    repro: str = Form(...),
    contact: str | None = Form(None),
    anonymous: bool = Form(False),
    allow_contact: bool = Form(False),
    steps: List[str] = Form([]),
    context: str = Form(""),
    attachments: List[UploadFile] = File([]),
    redis=Depends(get_redis),
) -> JSONResponse:
    """Accept and store a feedback entry."""
    if type not in {"issue", "improvement", "question"}:
        raise HTTPException(status_code=400, detail="invalid type")
    if severity not in {"blocker", "high", "medium", "low"}:
        raise HTTPException(status_code=400, detail="invalid severity")
    paths = []
    for file in attachments:
        if not file.filename:
            continue
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="invalid image type")
        content = await file.read()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="file too large")
        suffix = Path(file.filename).suffix or ".png"
        fname = f"{generate_id()}{suffix}"
        dest = UPLOAD_DIR / fname
        with open(dest, "wb") as f:
            f.write(content)
        paths.append(f"/static/feedback/{fname}")
    payload = {
        "title": title,
        "type": type,
        "severity": severity,
        "module": module,
        "description": description,
        "expected": expected,
        "actual": actual,
        "repro": repro,
        "contact": contact or "",
        "anonymous": json.dumps(bool(anonymous)),
        "allow_contact": json.dumps(bool(allow_contact)),
        "steps": json.dumps([s for s in steps if s.strip()]),
        "context": context,
        "attachments": json.dumps(paths),
        "status": "new",
    }
    fid = feedback_db.create_feedback(redis, payload)
    return JSONResponse({"id": fid})
