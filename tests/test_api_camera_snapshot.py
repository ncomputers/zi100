import subprocess


def test_api_camera_snapshot_success(client, monkeypatch, tmp_path):
    image_bytes = b"jpegdata"

    class CP:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output=None, text=None, check=None):
        output_path = cmd[-1]
        with open(output_path, "wb") as fh:
            fh.write(image_bytes)
        return CP()

    monkeypatch.setattr(subprocess, "run", fake_run)
    resp = client.post("/api/cameras/snapshot", json={"url": "rtsp://example"})
    assert resp.status_code == 200
    assert resp.content == image_bytes
    assert resp.headers["content-type"] == "image/jpeg"


def test_api_camera_snapshot_failure(client, monkeypatch):
    class CP:
        returncode = 1
        stdout = ""
        stderr = "boom"

    def fake_run(cmd, capture_output=None, text=None, check=None):
        return CP()

    monkeypatch.setattr(subprocess, "run", fake_run)
    resp = client.post("/api/cameras/snapshot", json={"url": "rtsp://example"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "snapshot failed"
