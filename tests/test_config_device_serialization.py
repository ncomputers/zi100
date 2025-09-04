import importlib
import sys
import uuid

import fakeredis

from core.config import load_config, save_config


def test_save_config_serializes_device_and_uuid(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    r = fakeredis.FakeRedis()
    session_id = uuid.uuid4()

    sys.modules.pop("torch", None)
    torch = importlib.import_module("torch")
    cfg = {
        "redis_url": "redis://localhost:6379/0",
        "device": torch.device("cpu"),
        "session": session_id,
    }

    save_config(cfg, str(cfg_path), r)
    loaded = load_config(str(cfg_path), r)

    assert loaded["device"] == "cpu"
    assert loaded["session"] == str(session_id)
