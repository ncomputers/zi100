import subprocess

import pytest

from utils import ffmpeg_snapshot


def test_capture_snapshot_uses_stdout_pipe(monkeypatch):
    expected = b"img"

    def fake_run(cmd, stdout, stderr, check):
        assert stdout is subprocess.PIPE
        assert stderr is subprocess.PIPE
        assert cmd[-1] == "pipe:1"
        assert cmd[cmd.index("-f") + 1] == "image2"

        class Result:
            returncode = 0
            stdout = expected
            stderr = b""

        return Result()

    monkeypatch.setattr(ffmpeg_snapshot.subprocess, "run", fake_run)
    assert ffmpeg_snapshot.capture_snapshot("rtsp://x") == expected


def test_capture_snapshot_raises_runtime_error(monkeypatch):
    def fake_run(cmd, stdout, stderr, check):
        class Result:
            returncode = 1
            stdout = b""
            stderr = b"boom"

        return Result()

    monkeypatch.setattr(ffmpeg_snapshot.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as excinfo:
        ffmpeg_snapshot.capture_snapshot("rtsp://x")
    assert "boom" in str(excinfo.value)
