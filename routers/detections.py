"""WebSocket endpoint emitting sample detections and demo page."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.websockets import WebSocketDisconnect

from utils.deps import get_templates


def get_stop_event() -> Any:
    return None


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/detections", response_class=HTMLResponse)
async def detections_page(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
) -> HTMLResponse:
    """Serve the simple detections demo page."""
    return templates.TemplateResponse("detections.html", {"request": request})


@router.websocket("/ws/detections")
async def detections_ws(
    ws: WebSocket,
    stop_event: Annotated[Any, Depends(get_stop_event)],
) -> None:
    """Stream random detection boxes as JSON over WebSocket."""
    await ws.accept()
    stop_event = cast("asyncio.Event | None", stop_event)

    async def _loop() -> None:
        while not (stop_event and stop_event.is_set()):
            box = {
                "x": random.random(),
                "y": random.random(),
                "width": random.random() * 0.5,
                "height": random.random() * 0.5,
            }
            await ws.send_json({"detections": [box]})
            await asyncio.sleep(0.5)

    try:
        await _loop()
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - unexpected errors
        logger.exception("Unexpected error in detections_ws")
    finally:
        await ws.close()
