"""Ensure profile page exposes user metadata."""

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routers import profile  # noqa: E402


class DummyRequest:
    def __init__(self):
        self.session = {"user": {"name": "alice"}}


class DummyTemplates:
    def TemplateResponse(self, name, context):
        return types.SimpleNamespace(context=context)


def test_profile_page_includes_user_metadata(tmp_path):
    cfg = {
        "user_name": "alice",
        "user_metadata": {
            "alice": {
                "company": "Acme",
                "department": "IT",
                "location": "HQ",
                "access_level": "admin",
            }
        },
    }
    profile.init_context(cfg, None, str(tmp_path))
    profile.templates = DummyTemplates()
    req = DummyRequest()
    resp = asyncio.run(profile.profile_page(req))
    meta = resp.context["meta"]
    assert meta["company"] == "Acme"
    assert meta["access_level"] == "admin"
