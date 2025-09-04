import pathlib
import sys

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from utils import preflight


def test_person_model_required(monkeypatch, tmp_path):
    cfg = {"enable_person_tracking": True, "person_model": str(tmp_path / "missing.pt")}
    monkeypatch.setattr(preflight, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(preflight, "torch", None)
    with pytest.raises(preflight.DependencyError, match="person_model"):
        preflight.check_dependencies(cfg, base_dir=tmp_path)
