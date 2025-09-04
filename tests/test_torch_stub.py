import importlib
import os
import sys
from pathlib import Path


def test_stub_loads_real_torch(tmp_path, monkeypatch):
    real = tmp_path / "torch.py"
    real.write_text("flag = 'real'")
    # Append path so import finds stub first, but stub locates our fake module
    monkeypatch.setattr(sys, "path", sys.path + [str(tmp_path)])
    sys.modules.pop("torch", None)
    mod = importlib.import_module("torch")
    assert getattr(mod, "flag") == "real"


def test_stub_handles_case_insensitive_paths(tmp_path, monkeypatch):
    real = tmp_path / "torch.py"
    real.write_text("flag = 'real'")

    case_diff = str(Path(__file__).resolve().parents[1]).upper()

    monkeypatch.setattr(os.path, "samefile", lambda a, b: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(os.path, "normcase", lambda p: p.lower())

    paths = sys.path.copy()
    paths.insert(1, case_diff)
    paths.insert(2, str(tmp_path))
    monkeypatch.setattr(sys, "path", paths)

    sys.modules.pop("torch", None)
    mod = importlib.import_module("torch")
    assert getattr(mod, "flag") == "real"
