import sys
import types
from datetime import datetime

import pytest

from routers.admin import users as admin_users
from schemas.user import UserCreate, UserUpdate

torch_mod = sys.modules.setdefault(
    "torch",
    types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        set_num_threads=lambda n: None,
    ),
)
if not hasattr(torch_mod, "device"):

    class device:
        def __init__(self, name: str):
            self.type = name

    torch_mod.device = device

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class DummyRedis:
    def set(self, key, value):
        pass


async def test_create_and_update_user(tmp_path):
    cfg = {}
    redis = DummyRedis()
    cfg_path = str(tmp_path / "cfg.json")
    new_user = UserCreate(
        username="alice", role="viewer", modules=[], email="a@b.com", name="Alice"
    )
    result = await admin_users.create_user(
        new_user, {"name": "admin"}, cfg=cfg, redis=redis, cfg_path=cfg_path
    )
    assert result == {"created": True}
    stored = cfg["users"][0]
    assert stored["status"] == "pending"
    assert stored["created_by"] == "admin"
    upd = UserUpdate(status="active", last_login=datetime(2023, 1, 1), mfa_enabled=True)
    result2 = await admin_users.update_user(
        "alice", upd, cfg=cfg, redis=redis, cfg_path=cfg_path
    )
    assert result2 == {"updated": True}
    assert stored["status"] == "active"
    assert stored["last_login"] == datetime(2023, 1, 1)
    assert stored["mfa_enabled"] is True


async def test_user_actions(tmp_path):
    cfg = {
        "users": [
            {
                "username": "bob",
                "password": "x",
                "role": "viewer",
                "modules": [],
                "status": "pending",
            }
        ]
    }
    redis = DummyRedis()
    cfg_path = str(tmp_path / "cfg.json")
    await admin_users.enable_user("bob", cfg=cfg, redis=redis, cfg_path=cfg_path)
    assert cfg["users"][0]["status"] == "active"
    await admin_users.disable_user("bob", cfg=cfg, redis=redis, cfg_path=cfg_path)
    assert cfg["users"][0]["status"] == "disabled"
    await admin_users.reset_password("bob", cfg=cfg, redis=redis, cfg_path=cfg_path)
    assert cfg["users"][0]["password"] == ""
    await admin_users.force_logout("bob", cfg=cfg, redis=redis, cfg_path=cfg_path)
    assert cfg["users"][0]["last_login"] is None
    export = await admin_users.export_users(cfg=cfg, redis=redis, cfg_path=cfg_path)
    assert export["users"][0]["username"] == "bob"
    assert "password" not in export["users"][0]

