import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_add_camera_invalid_local(client):
    payload = {"name": "Cam1", "type": "local", "url": "abcd1234"}
    res = client.post("/cameras", json=payload)
    assert res.status_code == 400
    assert res.json()["error"] == "invalid_local_camera"


def test_add_camera_local_numeric_ok(client):
    payload = {"name": "Cam2", "type": "local", "url": "0"}
    with patch("routers.cameras.start_tracker"):
        res = client.post("/cameras", json=payload)
    assert res.status_code == 200
    assert res.json()["added"]
