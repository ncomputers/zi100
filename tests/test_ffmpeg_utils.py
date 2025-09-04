from utils import ffmpeg as ffmpeg_utils


def test_build_timeout_flags_both(monkeypatch):
    monkeypatch.setattr(
        ffmpeg_utils,
        "_ffmpeg_has_option",
        lambda opt: opt in {"stimeout", "rw_timeout"},
    )
    assert ffmpeg_utils._build_timeout_flags(2.0) == [
        "-stimeout",
        "2000000",
        "-rw_timeout",
        "2000000",
    ]


def test_build_timeout_flags_partial(monkeypatch):
    monkeypatch.setattr(
        ffmpeg_utils, "_ffmpeg_has_option", lambda opt: opt == "stimeout"
    )
    assert ffmpeg_utils._build_timeout_flags(1.0) == ["-stimeout", "1000000"]


def test_build_timeout_flags_missing(monkeypatch):
    monkeypatch.setattr(ffmpeg_utils, "_ffmpeg_has_option", lambda opt: False)
    assert ffmpeg_utils._build_timeout_flags(1.0) == []


def test_build_preview_cmd_includes_flags(monkeypatch):
    monkeypatch.setattr(ffmpeg_utils, "_build_timeout_flags", lambda s: ["-test", "1"])
    cmd = ffmpeg_utils.build_preview_cmd("rtsp://x", "tcp", 1.0)
    assert ["-test", "1"] == cmd[cmd.index("-test") : cmd.index("-test") + 2]


def test_build_preview_cmd_downscale(monkeypatch):
    monkeypatch.setattr(ffmpeg_utils, "_build_timeout_flags", lambda s: [])
    cmd = ffmpeg_utils.build_preview_cmd("rtsp://x", "udp", 0, downscale=2)
    assert "-vf" in cmd
    idx = cmd.index("-vf") + 1
    assert cmd[idx] == "scale=trunc(iw/2/2)*2:trunc(ih/2/2)*2"
