import json

import pytest

import app


def _write_cfg(tmp_path, data):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_missing_redis_url(tmp_path):
    path = _write_cfg(tmp_path, {})
    with pytest.raises(SystemExit):
        app.init_app(config_path=path)


def test_unreachable_redis(tmp_path):
    path = _write_cfg(tmp_path, {"redis_url": "redis://localhost:9"})
    with pytest.raises(SystemExit):
        app.init_app(config_path=path)
