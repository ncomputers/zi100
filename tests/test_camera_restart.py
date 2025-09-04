"""Test that updating a camera restarts its tracker."""

import threading

import routers.cameras as cameras


def test_camera_restart(client, monkeypatch):
    calls = {}
    started = threading.Event()

    def fake_stop(cam_id, trackers):
        calls["stop"] = cam_id

    def fake_start(cam, cfg, trackers, redis):
        calls["start"] = cam["id"]
        started.set()
        return object()

    monkeypatch.setattr(cameras, "stop_tracker", fake_stop)
    monkeypatch.setattr(cameras, "start_tracker", fake_start)

    # ensure a camera exists for the test
    add = client.post("/cameras", json={"url": "test"})
    assert add.status_code == 200
    cam_id = add.json()["camera"]["id"]

    res = client.post(f"/camera/{cam_id}", json={"url": "changed"})
    assert res.status_code == 200
    data = res.json()
    assert data["updated"] is True
    assert data["restarted"] is True
    assert calls.get("stop") == cam_id
    assert started.wait(1)
    assert calls.get("start") == cam_id
