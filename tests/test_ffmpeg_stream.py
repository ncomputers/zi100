"""Purpose: Test ffmpeg stream module."""

# test_ffmpeg_stream.py
import io
import subprocess
import sys
import time
import types
from pathlib import Path

import ffmpeg
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Ensure OpenCV is available for downstream tests
import cv2  # noqa: F401

sys.modules.setdefault("torch", type("torch", (), {}))
sys.modules.setdefault("ultralytics", type("ultralytics", (), {"YOLO": object}))
sys.modules.setdefault("deep_sort_realtime", type("ds", (), {}))
sys.modules["deep_sort_realtime.deepsort_tracker"] = type("t", (), {"DeepSort": object})
sys.modules.setdefault(
    "loguru",
    type("loguru", (), {"logger": type("l", (), {"info": lambda *a, **k: None})()}),
)
sys.modules.setdefault("PIL", type("PIL", (), {}))
sys.modules.setdefault("PIL.Image", type("PIL.Image", (), {}))
sys.modules.setdefault("imagehash", type("imagehash", (), {}))
sys.modules.setdefault("ffmpeg", type("ffmpeg", (), {"probe": lambda *a, **k: {}}))

import modules.ffmpeg_stream as ffmpeg_stream
from config import set_config
from modules.ffmpeg_stream import FFmpegCameraStream


# DummyPopen class encapsulates dummypopen behavior
class DummyPopen:
    # __init__ routine
    def __init__(self, *args, **kwargs):
        self.stdout = io.BytesIO(b"\x01\x02\x03" * 4)
        self._poll = None

    # poll routine
    def poll(self):
        return self._poll

    # kill routine
    def kill(self):
        self._poll = 0


# Test ffmpeg stream read
def test_ffmpeg_stream_read(monkeypatch):
    # fake_popen routine
    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        return DummyPopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    stream = FFmpegCameraStream("rtsp://test", width=2, height=2, start_thread=False)
    import numpy as np

    stream.queue.append(np.zeros((2, 2, 3), dtype=np.uint8))
    ret, frame = stream.read()
    assert ret
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (2, 2, 3)
    stream.release()


def test_probe_updates_frame_size(monkeypatch):
    def fake_probe(*args, **kwargs):
        return {
            "streams": [
                {"codec_type": "video", "width": 320, "height": 240, "pix_fmt": "bgr24"}
            ]
        }

    monkeypatch.setattr(ffmpeg, "probe", fake_probe)
    stream = FFmpegCameraStream("rtsp://demo", start_thread=False)
    assert stream.width == 320
    assert stream.height == 240
    assert stream.frame_size == 320 * 240 * 3
    stream.release()


def test_probe_downscale_recomputes_frame_size(monkeypatch):
    def fake_probe(*args, **kwargs):
        return {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1280,
                    "height": 720,
                    "pix_fmt": "bgr24",
                }
            ]
        }

    monkeypatch.setattr(ffmpeg, "probe", fake_probe)
    stream = FFmpegCameraStream(
        "rtsp://demo", start_thread=False, test=True, downscale=2
    )
    assert stream.width == 640
    assert stream.height == 360
    assert stream.frame_size == 640 * 360 * 3
    stream.release()


# DummyPopenEOF class encapsulates dummypopeneof behavior
class DummyPopenEOF(DummyPopen):
    # __init__ routine
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # return less than frame size to trigger restart
        self.stdout = io.BytesIO(b"\x00\x01")


# Test ffmpeg stream restart
def test_ffmpeg_stream_restart(monkeypatch):
    calls = 0

    # fake_start routine
    def fake_start(self):
        nonlocal calls
        calls += 1
        self.proc = DummyPopenEOF()

    monkeypatch.setattr(FFmpegCameraStream, "_start_process", fake_start)
    stream = FFmpegCameraStream(
        "rtsp://admin:L281D8DA@192.168.31.10:554/cam/realmonitor?channel=1&subtype=1&unicast=true&proto=Onvif",
        width=2,
        height=2,
        start_thread=False,
    )
    ret, frame = stream.read()
    assert not ret
    assert frame is None
    # called once on init and once on short read
    assert calls >= 2
    stream.release()


# Test ffmpeg rtsp transport flag
def test_ffmpeg_command_construction(monkeypatch):
    captured = {}

    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        captured["cmd"] = cmd
        captured["stdin"] = stdin
        captured["stderr"] = stderr
        captured["bufsize"] = bufsize
        return DummyPopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    stream = FFmpegCameraStream("rtsp://demo", width=2, height=2, start_thread=False)
    cmd = captured["cmd"]
    assert "-nostdin" in cmd
    assert "-threads" in cmd and "1" in cmd
    assert "-rtsp_transport" in cmd and "tcp" in cmd
    assert "-rtsp_flags" in cmd and "prefer_tcp" in cmd
    assert "-rw_timeout" in cmd and "-stimeout" in cmd
    assert cmd.index("-rw_timeout") < cmd.index("rtsp://demo")
    assert "-reconnect" in cmd and "-reconnect_streamed" in cmd
    assert "-vf" in cmd and "scale=2:2" in ",".join(cmd)
    assert "-s" not in cmd

    assert "-fflags" in cmd and "nobuffer+discardcorrupt" in cmd
    assert cmd.count("-fflags") >= 2 and "+genpts" in cmd
    assert "-flags" in cmd and "low_delay" in cmd
    assert "-analyzeduration" in cmd and "1000000" in cmd
    assert "-probesize" in cmd and "500000" in cmd
    assert "-vcodec" in cmd and "rawvideo" in cmd
    assert "-pix_fmt" in cmd and "bgr24" in cmd
    assert "-f" in cmd and "rawvideo" in cmd
    assert captured["stderr"] is subprocess.PIPE
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["bufsize"] == 0
    stream.release()


def test_udp_transport_omits_rtsp_flags(monkeypatch):
    captured = {}

    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        captured["cmd"] = cmd
        return DummyPopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    stream = FFmpegCameraStream(
        "rtsp://demo",
        width=2,
        height=2,
        transport="udp",
        start_thread=False,
    )
    cmd = captured["cmd"]
    assert "-rtsp_transport" in cmd and "udp" in cmd
    assert "-rtsp_flags" not in cmd
    stream.release()


def test_retry_transports(monkeypatch):
    calls: list[str] = []

    class Proc:
        def __init__(self):
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()

        def poll(self):
            return None

        def kill(self):
            pass

    def fake_start(self):
        calls.append(self.transport)
        self.proc = Proc()
        self._first_frame_start = time.time()

    frame_map = {"tcp": None, "udp": b"\x00" * (2 * 2 * 3)}

    def fake_read_full(self):
        return frame_map[self.transport]

    monkeypatch.setattr(FFmpegCameraStream, "_start_process", fake_start)
    monkeypatch.setattr(FFmpegCameraStream, "_read_full_frame", fake_read_full)
    stream = FFmpegCameraStream("rtsp://demo", width=2, height=2, start_thread=False)
    stream.first_frame_timeout = 0.0
    ret, frame = stream.read()
    assert not ret and frame is None
    ret, frame = stream.read()
    assert ret and frame is not None
    assert stream.successful_transport == "udp"
    assert calls == ["tcp", "udp"]
    stream.release()


# Test that timeout flags precede the URL
def test_timeout_flag_position(monkeypatch):
    captured = {}

    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        captured["cmd"] = cmd
        return DummyPopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    stream = FFmpegCameraStream(
        "rtsp://demo",
        width=2,
        height=2,
        start_thread=False,
        extra_flags=["-rw_timeout", "1000000"],
    )
    cmd = captured["cmd"]
    assert "-rw_timeout" in cmd
    assert cmd.index("-rw_timeout") < cmd.index("rtsp://demo")
    stream.release()


# Test frame skipping
def test_ffmpeg_frame_skip(monkeypatch):
    frame_size = 2 * 2 * 3

    calls: list[int] = []

    def fake_full(self):
        if not calls:
            calls.append(1)
            return b"\x01" * frame_size
        return b"\x02" * frame_size

    class Proc:
        def poll(self):
            return None

        def kill(self):
            pass

        stdout = io.BytesIO()

    def fake_start(self):
        self.proc = Proc()
        self._first_frame_start = time.time()

    monkeypatch.setattr(FFmpegCameraStream, "_start_process", fake_start)
    monkeypatch.setattr(FFmpegCameraStream, "_read_full_frame", fake_full)
    stream = FFmpegCameraStream(
        "rtsp://demo", width=2, height=2, start_thread=False, frame_skip=2
    )
    ret, frame = stream.read()
    assert ret
    assert np.all(frame == 2)
    stream.release()


# Test ffmpeg error parsing
@pytest.mark.parametrize(
    "stderr, status, msg",
    [
        ("401 Unauthorized\n", "auth", "Authentication failed"),
        ("No route to host\n", "network", "No route to host"),
        ("Connection timed out\n", "timeout", "Connection timed out"),
        ("Unsupported codec\n", "error", "test"),
    ],
)
def test_ffmpeg_error_parsing(monkeypatch, stderr, status, msg):
    def fake_popen(
        cmd, stdin=None, stdout=None, stderr_pipe=None, bufsize=None, **kwargs
    ):
        return types.SimpleNamespace(
            stdout=io.BytesIO(),
            stderr=io.BytesIO(stderr.encode()),
        )

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    stream = FFmpegCameraStream("rtsp://demo", width=2, height=2, start_thread=False)
    if stream._stderr_thread:
        stream._stderr_thread.join(timeout=0.1)
    stream._log_failure("test")
    assert stream.last_status == status
    assert stream.last_error == msg


# Test draining of stderr
def test_stderr_drain(monkeypatch):
    frame_size = 2 * 2 * 3

    def fake_full(self):
        return b"\x01" * frame_size

    class Proc:
        def __init__(self):
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO(b"spam\n" * 1000)

        def poll(self):
            return None

        def kill(self):
            pass

    def fake_start(self):
        self.proc = Proc()
        self._stderr_buffer.clear()
        for line in self.proc.stderr.readlines():
            self._stderr_buffer.append(line.decode().rstrip())
        self._first_frame_start = time.time()

    monkeypatch.setattr(FFmpegCameraStream, "_start_process", fake_start)
    monkeypatch.setattr(FFmpegCameraStream, "_read_full_frame", fake_full)
    stream = FFmpegCameraStream("rtsp://demo", width=2, height=2, start_thread=False)

    frames = []
    for _ in range(3):
        ret, frame = stream.read()
        assert ret
        frames.append(frame.copy())

    assert len(frames) == 3
    if stream._stderr_thread:
        stream._stderr_thread.join(timeout=0.1)
    assert len(stream._stderr_buffer) == 200
    stream.release()


def test_stderr_stall_and_limit(monkeypatch):
    frame_size = 2 * 2 * 3
    stdout_data = b"\x01" * frame_size

    class SlowStderr:
        def __init__(self):
            self.lines = [f"line{i}\n".encode() for i in range(250)]

        def readline(self):
            if self.lines:
                return self.lines.pop(0)
            time.sleep(0.05)
            return b""

    class VerbosePopen:
        def __init__(self, *a, **k):
            self.stdout = io.BytesIO(stdout_data)
            self.stderr = SlowStderr()
            self._poll = None

        def poll(self):
            return self._poll

        def kill(self):
            self._poll = 0

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: VerbosePopen())
    stream = FFmpegCameraStream("rtsp://demo", width=2, height=2, start_thread=False)
    ret, frame = stream.read()
    assert ret
    if stream._stderr_thread:
        stream._stderr_thread.join(timeout=1)
    assert len(stream._stderr_buffer) == 200
    stream.release()


# Test ffmpeg watermark flags
def test_ffmpeg_watermark_flags(monkeypatch):
    captured = {}

    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        captured["cmd"] = cmd
        return DummyPopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ffmpeg_stream, "_supports_drop", lambda: True)
    set_config(
        {
            "ffmpeg_high_watermark": 10,
            "ffmpeg_low_watermark": 5,
            "duplicate_filter_enabled": True,
        }
    )
    stream = FFmpegCameraStream("rtsp://demo", width=2, height=2, start_thread=False)
    cmd = captured["cmd"]
    assert "-h" in cmd and "10" in cmd
    assert "-l" in cmd and "5" in cmd
    assert "-flags" in cmd and "low_delay" in cmd
    assert stream.dup_filter is None
    stream.release()
    set_config({})


def test_ffmpeg_watermark_flags_no_drop_support(monkeypatch):
    captured = {}

    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        captured["cmd"] = cmd
        return DummyPopen()

    def fake_run(cmd, capture_output=None, text=None, check=False):
        return types.SimpleNamespace(stdout="help output")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ffmpeg_stream.subprocess, "run", fake_run)
    ffmpeg_stream._supports_drop.cache_clear()
    set_config(
        {
            "ffmpeg_high_watermark": 10,
            "ffmpeg_low_watermark": 5,
            "duplicate_filter_enabled": True,
        }
    )
    stream = FFmpegCameraStream("rtsp://demo", width=2, height=2, start_thread=False)
    cmd = captured["cmd"]
    assert "-drop" not in cmd and "-h" not in cmd and "-l" not in cmd
    assert stream.proc is not None
    assert stream.dup_filter is not None
    stream.release()
    set_config({})


def test_duplicate_filter_fallback(monkeypatch):
    captured = {}

    def fake_popen(cmd, stdout=None, stderr=None, bufsize=None):
        captured["cmd"] = cmd
        return DummyPopen()

    def fake_run(cmd, capture_output=None, text=None, check=False):
        return types.SimpleNamespace(stdout="help output")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ffmpeg_stream.subprocess, "run", fake_run)
    ffmpeg_stream._supports_drop.cache_clear()
    set_config({"ffmpeg_high_watermark": 10, "duplicate_filter_enabled": True})
    stream = FFmpegCameraStream("rtsp://demo", width=2, height=2, start_thread=False)
    assert stream.dup_filter is not None
    assert "-drop" not in captured["cmd"]
    stream.release()
    set_config({})


# Test ffmpeg extra_flags with string input
def test_ffmpeg_extra_flags_str(monkeypatch):
    # fake_popen routine
    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        return DummyPopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    stream = FFmpegCameraStream(
        "rtsp://demo",
        width=2,
        height=2,
        start_thread=False,
        extra_flags="-vf scale=1280:720 -an",
    )
    assert stream.extra_flags == ["-vf", "scale=1280:720", "-an"]
    stream.release()


# Test ffmpeg extra_flags with list input
def test_ffmpeg_extra_flags_list(monkeypatch):
    # fake_popen routine
    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        return DummyPopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    flags = ["-vf", "scale=1280:720", "-an"]
    stream = FFmpegCameraStream(
        "rtsp://demo",
        width=2,
        height=2,
        start_thread=False,
        extra_flags=flags,
    )
    assert stream.extra_flags == flags
    stream.release()


# Test ffmpeg frame skipping
class DummyPopenFrames:
    def __init__(self, *args, **kwargs):
        self.stdout = DummyStdout()
        self.stderr = io.BytesIO()
        self._poll = None

    def poll(self):
        return self._poll

    def kill(self):
        self._poll = 0


class DummyStdout:
    def __init__(self):
        self.idx = 0

    def read(self, n):
        data = bytes([self.idx % 256]) * n
        self.idx += 1
        return data


def test_ffmpeg_stream_frame_skip(monkeypatch):
    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        return DummyPopenFrames()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    stream = FFmpegCameraStream("rtsp://demo", width=1, height=1, start_thread=False)
    frame_skip = 2
    processed = []
    for i in range(6):
        ret, frame = stream.read()
        assert ret
        if i % (frame_skip + 1) == 0:
            processed.append(frame.copy())
    assert len(processed) == 2
    assert processed[0][0, 0, 0] == 0
    assert processed[1][0, 0, 0] == frame_skip + 1
    stream.release()


# Test handling of broken ffmpeg process
class DummyPopenBroken:
    def __init__(self, *args, **kwargs):
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
        self._poll = 1

    def poll(self):
        return self._poll

    def kill(self):
        self._poll = 0


def test_ffmpeg_stream_handles_broken_process(monkeypatch):
    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        return DummyPopenBroken()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    stream = FFmpegCameraStream(
        "rtsp://demo", width=1, height=1, start_thread=False, reconnect_delay=0
    )
    ret, frame = stream.read()
    assert not ret
    assert frame is None
    assert stream.proc is not None

    stream.release()


class _VanishingStdout(io.BytesIO):
    def __init__(self, proc, stream):
        super().__init__(b"\x00\x01\x02")
        self.proc = proc
        self.stream = stream

    def read(self, size=-1):
        data = super().read(size)
        self.stream.proc = None
        self.proc.stdout = None
        self.proc._poll = 1
        return data


class DummyPopenVanishing:
    def __init__(self, stream, *args, **kwargs):
        self.stdout = _VanishingStdout(self, stream)
        self.stderr = io.BytesIO()
        self._poll = None

    def poll(self):
        return self._poll

    def kill(self):
        self._poll = 0


def test_ffmpeg_stream_handles_disappearing_process(monkeypatch):
    def fake_start(self):
        self.proc = DummyPopenVanishing(self)

    monkeypatch.setattr(FFmpegCameraStream, "_start_process", fake_start)
    stream = FFmpegCameraStream("rtsp://demo", width=2, height=2, start_thread=False)
    ret, frame = stream.read()
    assert not ret
    assert frame is None

    stream.release()


def test_capture_thread_without_process(monkeypatch):
    def fake_start(self):
        self.proc = None

    monkeypatch.setattr(FFmpegCameraStream, "_start_process", fake_start)
    stream = FFmpegCameraStream("rtsp://demo", width=1, height=1)
    time.sleep(0.1)
    assert stream.thread.is_alive()

    stream.release()


def test_no_scale_when_size_unspecified(monkeypatch):
    captured = {}

    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, bufsize=None, **kwargs):
        captured["cmd"] = cmd
        return DummyPopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        ffmpeg_stream.ffmpeg,
        "probe",
        lambda *a, **k: {
            "streams": [
                {"codec_type": "video", "width": 640, "height": 480, "pix_fmt": "bgr24"}
            ]
        },
    )
    stream = FFmpegCameraStream("rtsp://demo", start_thread=False)
    cmd = captured["cmd"]
    assert "-s" not in cmd
    stream.release()


def test_build_ffmpeg_cmd_tcp(monkeypatch):
    monkeypatch.setattr(ffmpeg, "probe", lambda *a, **k: {})
    monkeypatch.setattr(FFmpegCameraStream, "_start_process", lambda self: None)
    monkeypatch.setattr(ffmpeg_stream, "_supports_drop", lambda: False)
    stream = FFmpegCameraStream("rtsp://demo", start_thread=False)
    cmd = stream.build_ffmpeg_cmd()
    assert "-rtsp_transport" in cmd and "tcp" in cmd
    assert "-rtsp_flags" in cmd and "prefer_tcp" in cmd
    stream.release()


def test_build_ffmpeg_cmd_udp(monkeypatch):
    monkeypatch.setattr(ffmpeg, "probe", lambda *a, **k: {})
    monkeypatch.setattr(FFmpegCameraStream, "_start_process", lambda self: None)
    monkeypatch.setattr(ffmpeg_stream, "_supports_drop", lambda: False)
    stream = FFmpegCameraStream("rtsp://demo", transport="udp", start_thread=False)
    cmd = stream.build_ffmpeg_cmd()
    assert "-rtsp_transport" in cmd and "udp" in cmd
    assert "-rtsp_flags" not in cmd
    stream.release()


def test_build_ffmpeg_cmd_test_mode(monkeypatch):
    monkeypatch.setattr(ffmpeg, "probe", lambda *a, **k: {})
    monkeypatch.setattr(FFmpegCameraStream, "_start_process", lambda self: None)
    monkeypatch.setattr(ffmpeg_stream, "_supports_drop", lambda: False)
    stream = FFmpegCameraStream(
        "rtsp://demo", width=640, height=480, test=True, start_thread=False
    )
    cmd = stream.build_ffmpeg_cmd()
    assert "-t" in cmd and "2" in cmd
    assert "-vf" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "fps=1" in vf and "scale=640:480" in vf
    stream.release()


def test_build_ffmpeg_cmd_downscale(monkeypatch):
    monkeypatch.setattr(ffmpeg, "probe", lambda *a, **k: {})
    monkeypatch.setattr(FFmpegCameraStream, "_start_process", lambda self: None)
    monkeypatch.setattr(ffmpeg_stream, "_supports_drop", lambda: False)
    stream = FFmpegCameraStream(
        "rtsp://demo", test=True, downscale=2, start_thread=False
    )
    cmd = stream.build_ffmpeg_cmd()
    assert "-vf" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "fps=1" in vf and "scale=iw/2:ih/2" in vf
    stream.release()


def test_build_ffmpeg_cmd_mirror_orientation(monkeypatch):
    monkeypatch.setattr(ffmpeg, "probe", lambda *a, **k: {})
    monkeypatch.setattr(FFmpegCameraStream, "_start_process", lambda self: None)
    monkeypatch.setattr(ffmpeg_stream, "_supports_drop", lambda: False)
    stream = FFmpegCameraStream(
        "rtsp://demo", mirror=True, orientation="horizontal", start_thread=False
    )
    cmd = stream.build_ffmpeg_cmd()
    vf = cmd[cmd.index("-vf") + 1]
    assert "hflip" in vf and "transpose" not in vf
    stream.release()
