from pathlib import Path

import fakeredis
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from routers.face_db import router


def client():
    app = FastAPI()
    app.state.config = {"branding": {"company_logo_url": ""}, "features": {}, "license_info": {}}
    app.state.redis_client = fakeredis.FakeRedis(decode_responses=True)
    tmpl_dir = Path(__file__).resolve().parents[1] / "templates"
    app.state.templates = Jinja2Templates(directory=str(tmpl_dir))
    app.include_router(router)
    app.add_middleware(SessionMiddleware, secret_key="test")
    return TestClient(app)


def test_face_db_page_route():
    with client() as c:
        resp = c.get("/face-db")
        assert resp.status_code == 200
        assert "Add Face" in resp.text
