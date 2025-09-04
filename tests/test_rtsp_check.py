import json
import subprocess
import types

import pytest

from modules import stream_probe


class FakeProc:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr

    def communicate(self, timeout=None):
        return ("", self.stderr)

    def kill(self):
        self.killed = True

    def poll(self):
        return self.returncode


def test_check_rtsp_bad_url():
    res = stream_probe.check_rtsp("http://example")
    assert res["ok"] is False
    assert res["error"] == "BAD_URL"


def test_check_rtsp_no_video_stream(monkeypatch):
    def fake_run(*a, **k):
        return types.SimpleNamespace(stdout=json.dumps({"streams": []}), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    res = stream_probe.check_rtsp("rtsp://example")
    assert res["ok"] is False
    assert res["error"] == "NO_VIDEO_STREAM"


def test_check_rtsp_auth_failed(monkeypatch):
    def fake_run(*a, **k):
        data = {"streams": [{"codec_type": "video", "codec_name": "h264"}]}
        return types.SimpleNamespace(stdout=json.dumps(data), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    fake = FakeProc(returncode=1, stderr="RTSP/1.0 401 Unauthorized\n")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: fake)
    res = stream_probe.check_rtsp("rtsp://example")
    assert res["ok"] is False
    assert res["error"] == "AUTH_FAILED"
    assert "stderr_tail" in res
