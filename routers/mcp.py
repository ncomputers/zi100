"""MCP testing routes for OpenAI chat."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

cfg: dict = {}
templates: Jinja2Templates


def init_context(config: dict, templates_path: str) -> None:
    """Initialize shared module state."""
    global cfg, templates
    cfg = config
    templates = Jinja2Templates(directory=templates_path)


@router.get("/mcp", response_class=HTMLResponse)
async def mcp_page(request: Request) -> HTMLResponse:
    api_key = bool(request.session.get("openai_api_key"))
    return templates.TemplateResponse(
        "mcp.html", {"request": request, "cfg": cfg, "api_key": api_key}
    )


@router.post("/mcp/save_key")
async def save_key(request: Request) -> RedirectResponse:
    form = await request.form()
    request.session["openai_api_key"] = form.get("api_key", "").strip()
    return RedirectResponse("/mcp", status_code=302)


@router.post("/mcp/chat")
async def chat(request: Request) -> JSONResponse:
    api_key = request.session.get("openai_api_key")
    if not api_key:
        return JSONResponse({"error": "API key not set"}, status_code=400)
    data = await request.json()
    message = data.get("message", "")
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": message}],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=body
        )
    reply = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    return JSONResponse({"reply": reply})
