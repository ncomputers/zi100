import asyncio
from types import SimpleNamespace

from startup import preload_models


def test_preload_models(monkeypatch):
    calls = []

    def fake_get_yolo(path, device):
        calls.append(("yolo", path))

    def fake_get_insightface(name):
        calls.append(("face", name))

    monkeypatch.setattr("startup.get_yolo", fake_get_yolo)
    monkeypatch.setattr("startup.get_insightface", fake_get_insightface)
    monkeypatch.setattr(
        "utils.gpu.get_device", lambda device=None: SimpleNamespace(type="cpu")
    )

    cfg = {
        "person_model": "p.pt",
        "plate_model": "pl.pt",
        "features": {"visitor_mgmt": True},
    }

    asyncio.run(preload_models(cfg))

    assert ("yolo", "p.pt") in calls
    assert ("yolo", "pl.pt") in calls
    assert ("face", "buffalo_l") in calls
