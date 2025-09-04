import sys
import types
from unittest import mock

import utils.gpu as gpu


def _make_torch(
    is_cuda_available: bool,
    *,
    device_count: int = 0,
    free_mem: int = 2 * 1024**3,
    name_error: bool = False,
    with_version: bool = True,
):
    def get_device_name(idx: int):
        if name_error:
            raise RuntimeError("boom")
        return f"GPU {idx}"

    cuda_ns = types.SimpleNamespace(
        is_available=lambda: is_cuda_available,
        device_count=lambda: device_count,
        current_device=lambda: 0,
        mem_get_info=lambda device=None: (free_mem, free_mem * 2),
        get_device_name=get_device_name,
    )
    attrs = {
        "cuda": cuda_ns,
        "device": lambda d: types.SimpleNamespace(type=str(d).split(":")[0]),
        "backends": types.SimpleNamespace(
            cudnn=types.SimpleNamespace(version=lambda: "test")
        ),
    }
    if with_version:
        attrs["version"] = types.SimpleNamespace(cuda="test")
    return types.SimpleNamespace(**attrs)


def _capture_logger():
    records: list[str] = []
    handler_id = gpu.logger.add(lambda msg: records.append(msg), format="{message}")
    return records, handler_id


def _capture_logger():
    records: list[str] = []
    handler_id = gpu.logger.add(lambda msg: records.append(msg), format="{message}")
    return records, handler_id


def test_probe_cuda_success():
    fake_torch = _make_torch(True, device_count=1)
    with mock.patch.object(gpu, "torch", fake_torch):
        ok, count, err = gpu.probe_cuda()
    assert ok is True
    assert count == 1
    assert err is None


def test_probe_cuda_name_failure():
    fake_torch = _make_torch(True, device_count=1, name_error=True)
    with mock.patch.object(gpu, "torch", fake_torch):
        ok, count, err = gpu.probe_cuda()
    assert ok is False
    assert count == 1
    assert err == "boom"


def test_probe_cuda_no_torch():
    with mock.patch.object(gpu, "torch", None):
        ok, count, err = gpu.probe_cuda()
    assert (ok, count) == (False, 0)
    assert err == "torch missing"


def test_get_device_cpu_fallback(monkeypatch):
    fake_torch = _make_torch(False)
    monkeypatch.setattr(gpu, "torch", fake_torch)
    dev = gpu.get_device()
    assert dev.type == "cpu"


def test_get_device_logs_details(monkeypatch):
    fake_torch = _make_torch(False)
    monkeypatch.setattr(gpu, "torch", fake_torch)
    records, handler = _capture_logger()
    try:
        gpu.get_device()
    finally:
        gpu.logger.remove(handler)
    text = " ".join(records)
    assert "is_available=False" in text
    assert "device_count=0" in text


def test_get_device_selects_cuda(monkeypatch):
    fake_torch = _make_torch(True)
    monkeypatch.setattr(gpu, "torch", fake_torch)
    dev = gpu.get_device()
    assert dev.type == "cuda"


def test_get_device_uses_device_count(monkeypatch):
    fake_torch = _make_torch(False, device_count=1)
    monkeypatch.setattr(gpu, "torch", fake_torch)
    dev = gpu.get_device()
    assert dev.type == "cuda"


def test_get_device_memory_threshold(monkeypatch):
    fake_torch = _make_torch(True, free_mem=0)
    monkeypatch.setattr(gpu, "torch", fake_torch)
    dev = gpu.get_device(min_gb=1.0)
    assert dev.type == "cpu"


def test_get_device_name_probe_failure(monkeypatch):
    fake_torch = _make_torch(True, name_error=True)
    monkeypatch.setattr(gpu, "torch", fake_torch)
    records, handler = _capture_logger()
    try:
        dev = gpu.get_device()
    finally:
        gpu.logger.remove(handler)
    assert dev.type == "cpu"
    text = " ".join(records)
    assert "probe_error=boom" in text


def test_get_device_logs_onnxruntime(monkeypatch):
    fake_torch = _make_torch(False)
    monkeypatch.setattr(gpu, "torch", fake_torch)
    fake_ort = types.SimpleNamespace(
        set_default_providers=lambda providers: None,
        get_available_providers=lambda: ["CPUExecutionProvider"],
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    records, handler = _capture_logger()
    try:
        gpu.get_device()
    finally:
        gpu.logger.remove(handler)
        monkeypatch.delitem(sys.modules, "onnxruntime", raising=False)
    text = " ".join(records)
    assert "ONNXRuntime providers" in text
    assert "ONNXRuntime running on CPU" in text


def test_configure_onnxruntime_cpu(monkeypatch):
    fake_ort = types.SimpleNamespace(
        set_default_providers=lambda providers: None,
        get_available_providers=lambda: ["CPUExecutionProvider"],
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    cfg: dict = {}
    records, handler = _capture_logger()
    try:
        provider = gpu.configure_onnxruntime(cfg)
    finally:
        gpu.logger.remove(handler)
        monkeypatch.delitem(sys.modules, "onnxruntime", raising=False)
    text = " ".join(records)
    assert provider == "CPUExecutionProvider"
    assert cfg["onnxruntime_provider"] == "CPUExecutionProvider"
    assert "ONNXRuntime providers" in text
    assert "running on CPU" in text


def test_configure_onnxruntime_gpu(monkeypatch):
    fake_ort = types.SimpleNamespace(
        set_default_providers=lambda providers: None,
        get_available_providers=lambda: [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ],
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    cfg: dict = {}
    records, handler = _capture_logger()
    try:
        provider = gpu.configure_onnxruntime(cfg)
    finally:
        gpu.logger.remove(handler)
        monkeypatch.delitem(sys.modules, "onnxruntime", raising=False)
    text = " ".join(records)
    assert provider == "CUDAExecutionProvider"
    assert cfg["onnxruntime_provider"] == "CUDAExecutionProvider"
    assert "GPU acceleration enabled" in text


def test_get_device_without_torch_version(monkeypatch):
    fake_torch = _make_torch(False, with_version=False)
    monkeypatch.setattr(gpu, "torch", fake_torch)
    records, handler = _capture_logger()
    try:
        dev = gpu.get_device()
    finally:
        gpu.logger.remove(handler)
    assert dev.type == "cpu"
    text = " ".join(records)
    assert "torch_cuda=unknown" in text
