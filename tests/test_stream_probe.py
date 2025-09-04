import json
import subprocess
import types
from itertools import product

import pytest

from modules import stream_probe


class FakeResult(types.SimpleNamespace):
    pass


def test_probe_stream_selects_best(monkeypatch):
    sample_seconds = 2

    tcp_cmd = []

    def fake_run(cmd, *a, **k):
        nonlocal tcp_cmd
        if cmd[0] == "ffprobe":
            data = {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 640,
                        "height": 480,
                        "avg_frame_rate": "30/1",
                    }
                ]
            }
            return FakeResult(stdout=json.dumps(data), stderr="")
        # ffmpeg trials
        transport = cmd[cmd.index("-rtsp_transport") + 1]
        if transport == "tcp":
            tcp_cmd = cmd[:]
        hw = "-hwaccel" in cmd
        frames = 10
        if transport == "udp" and hw:
            frames = 30
        stderr = f"frame={frames} fps={frames/sample_seconds}\n"
        return FakeResult(stdout="", stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = stream_probe.probe_stream("rtsp://test", sample_seconds, True)
    assert summary["transport"] == "udp"
    assert summary["hwaccel"] is True
    assert summary["metadata"]["codec"] == "h264"
    assert summary["frames"] == 30
    assert "-rtsp_flags" in tcp_cmd and "prefer_tcp" in tcp_cmd


@pytest.mark.parametrize(
    "transport,hwaccel",
    list(product(["tcp", "udp"], [False, True])),
)
def test_build_trial_cmd_combinations(transport, hwaccel):
    url = "rtsp://cam"
    sample_seconds = 2
    cmd = stream_probe._build_trial_cmd(url, transport, hwaccel, sample_seconds)
    assert cmd[:3] == ["ffmpeg", "-rtsp_transport", transport]
    if transport == "tcp":
        assert "-rtsp_flags" in cmd and "prefer_tcp" in cmd
    else:
        assert "-rtsp_flags" not in cmd
    if hwaccel:
        assert "-hwaccel" in cmd and "auto" in cmd
    else:
        assert "-hwaccel" not in cmd
    idx = cmd.index("-i")
    assert cmd[idx + 1 :] == [
        url,
        "-t",
        str(sample_seconds),
        "-f",
        "null",
        "-",
    ]
