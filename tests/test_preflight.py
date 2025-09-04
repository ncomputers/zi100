import importlib

import pytest

import utils.preflight as preflight_mod


def _load_real():
    return importlib.reload(preflight_mod)


def _restore_stub():
    preflight_mod.check_dependencies = lambda *a, **k: None


def test_binaries_missing(monkeypatch, tmp_path):
    pf = _load_real()
    model = tmp_path / "person.pt"
    model.write_text("x")

    monkeypatch.setattr(pf, "which", lambda name: None)
    cfg = {"person_model": str(model)}
    with pytest.raises(pf.DependencyError):
        pf.check_dependencies(cfg, tmp_path)
    _restore_stub()


def test_single_binary_missing(monkeypatch, tmp_path):
    pf = _load_real()
    model = tmp_path / "person.pt"
    model.write_text("x")

    def fake_which(name: str):
        return None if name == "ffmpeg" else "/usr/bin/" + name

    monkeypatch.setattr(pf, "which", fake_which)
    cfg = {"person_model": str(model)}
    pf.check_dependencies(cfg, tmp_path)
    assert cfg["ffmpeg_available"] is False
    assert cfg["gst_available"] is True
    _restore_stub()


def test_model_missing(monkeypatch, tmp_path):
    pf = _load_real()
    monkeypatch.setattr(pf, "which", lambda name: "/usr/bin/" + name)
    cfg = {"person_model": str(tmp_path / "missing.pt")}
    with pytest.raises(pf.DependencyError) as exc:
        pf.check_dependencies(cfg, tmp_path)
    assert "missing.pt" in str(exc.value)
    _restore_stub()


def test_all_present(monkeypatch, tmp_path):
    pf = _load_real()
    monkeypatch.setattr(pf, "which", lambda name: "/usr/bin/" + name)
    model = tmp_path / "model.pt"
    model.write_text("x")
    cfg = {
        "person_model": str(model),
        "ppe_model": str(model),
        "plate_model": str(model),
    }
    # should not raise
    pf.check_dependencies(cfg, tmp_path)
    _restore_stub()


def test_cuda_required_missing(monkeypatch, tmp_path):
    pf = _load_real()
    monkeypatch.setattr(pf, "which", lambda name: "/usr/bin/" + name)

    class DummyCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class DummyTorch:
        cuda = DummyCuda()

    monkeypatch.setattr(pf, "torch", DummyTorch())
    model = tmp_path / "model.pt"
    model.write_text("x")
    cfg = {"person_model": str(model), "require_cuda": True}
    with pytest.raises(pf.DependencyError):
        pf.check_dependencies(cfg, tmp_path)
    _restore_stub()


def test_cuda_memory_check(monkeypatch, tmp_path):
    pf = _load_real()
    monkeypatch.setattr(pf, "which", lambda name: "/usr/bin/" + name)

    class DummyCuda:
        @staticmethod
        def is_available() -> bool:
            return True

    class DummyTorch:
        cuda = DummyCuda()

    monkeypatch.setattr(pf, "torch", DummyTorch())

    called = {}

    def fake_assert_memory(min_gb: float) -> None:
        called["val"] = min_gb

    monkeypatch.setattr(pf, "assert_memory", fake_assert_memory)

    model = tmp_path / "model.pt"
    model.write_text("x")
    cfg = {"person_model": str(model), "min_gpu_memory_gb": 1}
    pf.check_dependencies(cfg, tmp_path)
    assert called["val"] == 1
    _restore_stub()
