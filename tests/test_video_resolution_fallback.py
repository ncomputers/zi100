import logging
import subprocess

import utils.video as video


def test_get_stream_resolution_calledprocesserror(monkeypatch, caplog):
    def _raise(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ffprobe")

    monkeypatch.setattr(video.subprocess, "run", _raise)
    with caplog.at_level(logging.WARNING):
        res = video.get_stream_resolution("rtsp://example")
    assert res == (640, 480)
    assert "CalledProcessError" in caplog.text


def test_get_stream_resolution_oserror(monkeypatch, caplog):
    def _raise(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(video.subprocess, "run", _raise)
    with caplog.at_level(logging.WARNING):
        res = video.get_stream_resolution("rtsp://example")
    assert res == (640, 480)
    assert "OSError" in caplog.text


def test_get_stream_resolution_valueerror(monkeypatch, caplog):
    def _run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            stdout='{"streams":[{"width":"bad","height":480}]}',
            stderr="",
        )

    monkeypatch.setattr(video.subprocess, "run", _run)
    with caplog.at_level(logging.WARNING):
        res = video.get_stream_resolution("rtsp://example")
    assert res == (640, 480)
    assert "ValueError" in caplog.text
