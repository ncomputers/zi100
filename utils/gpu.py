"""GPU utility functions."""

from __future__ import annotations

from loguru import logger

try:  # optional heavy dependency
    import torch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional in tests
    torch = None


def probe_cuda() -> tuple[bool, int, str | None]:
    """Check CUDA availability and return diagnostics."""

    if torch is None or not hasattr(torch, "cuda"):
        logger.debug("torch not available, skipping CUDA probe")
        return False, 0, "torch missing"

    try:
        cuda_available = bool(torch.cuda.is_available())
    except Exception as exc:  # pragma: no cover - unexpected failure
        logger.warning(f"torch.cuda.is_available() failed: {exc}")
        return False, 0, str(exc)

    try:
        device_count = int(getattr(torch.cuda, "device_count", lambda: 0)())
    except Exception as exc:  # pragma: no cover - unexpected failure
        logger.warning(f"torch.cuda.device_count() failed: {exc}")
        return False, 0, str(exc)

    logger.info(
        f"CUDA probe: is_available={cuda_available}, device_count={device_count}"
    )

    has_cuda = cuda_available or device_count > 0
    error = None
    if has_cuda:
        try:
            name = torch.cuda.get_device_name(0)
            logger.info(f"CUDA device name: {name}")
        except Exception as exc:
            logger.warning(f"CUDA device probe failed: {exc}")
            has_cuda = False
            error = str(exc)

    return has_cuda, device_count, error


def configure_onnxruntime(cfg: dict | None = None) -> str:
    """Attempt to initialize ONNX Runtime with CUDA support.

    The function prefers the ``CUDAExecutionProvider`` and falls back to CPU
    execution when it is unavailable. The active provider name is stored in
    ``cfg['onnxruntime_provider']`` when a configuration dictionary is
    supplied.

    Args:
        cfg: Optional configuration mapping to update with the active provider.

    Returns:
        str: Name of the active execution provider or ``"missing"`` when
        ONNX Runtime is not installed.
    """

    try:  # pragma: no cover - optional dependency
        import onnxruntime as ort  # type: ignore
    except Exception as exc:  # pragma: no cover - probe best effort
        logger.info(f"ONNXRuntime not available: {exc}")
        if cfg is not None:
            cfg["onnxruntime_provider"] = "missing"
        return "missing"

    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if hasattr(ort, "set_default_providers"):
        try:
            ort.set_default_providers(providers)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning(f"Failed to set CUDA provider: {exc}")
            try:
                ort.set_default_providers(["CPUExecutionProvider"])
            except Exception:
                pass

    available = ort.get_available_providers()
    logger.info(f"ONNXRuntime providers: {available}")
    if "CUDAExecutionProvider" in available:
        logger.info("ONNXRuntime GPU acceleration enabled")
        provider = "CUDAExecutionProvider"
    else:
        logger.warning("ONNXRuntime running on CPU")
        provider = "CPUExecutionProvider"

    if cfg is not None:
        cfg["onnxruntime_provider"] = provider
    return provider


def assert_memory(min_gb: float, device: "torch.device | int | None" = None) -> None:
    """Ensure at least ``min_gb`` GB of free GPU memory is available.

    Args:
        min_gb: Minimum required free GPU memory.
        device: CUDA device to inspect. Defaults to the current device.

    Raises:
        RuntimeError: If available GPU memory is below ``min_gb``.
    """
    if torch is None or not torch.cuda.is_available():
        # No GPU available; nothing to assert.
        return
    if device is None:
        device = torch.device(f"cuda:{torch.cuda.current_device()}")
    free, _ = torch.cuda.mem_get_info(device)
    free_gb = free / (1024**3)
    logger.debug(f"GPU free memory: {free_gb:.2f} GB")
    if free_gb < min_gb:
        raise RuntimeError(
            f"Insufficient GPU memory: {free_gb:.2f} GB available, {min_gb} GB required"
        )


def get_device(
    device: "torch.device | str | None" = None,
    min_gb: float | None = None,
) -> "torch.device | str":
    """Resolve a device specification and optionally validate GPU memory.

    ``device`` may be ``"auto"`` or ``None`` to prefer CUDA when available.
    When ``min_gb`` is provided, the selected CUDA device must have at least
    that much free memory or the function falls back to CPU.

    Args:
        device: Requested device string or object.
        min_gb: Minimum required free GPU memory in GB.

    Returns:
        torch.device | str: Resolved device instance or ``"cpu"`` when ``torch``
        is unavailable.


    Raises:
        RuntimeError: If a CUDA device is requested but not present.
    """
    if torch is None or not hasattr(torch, "device"):
        logger.debug("torch not available, using CPU")
        return "cpu"

    has_cuda, device_count, probe_error = probe_cuda()
    configure_onnxruntime()

    if device is None or (isinstance(device, str) and device == "auto"):
        if has_cuda:
            dev = torch.device("cuda:0")
        else:
            version_mod = getattr(torch, "version", None)
            cuda_version = getattr(version_mod, "cuda", "unknown")
            cudnn_backend = getattr(getattr(torch, "backends", None), "cudnn", None)
            cudnn_version = getattr(cudnn_backend, "version", lambda: "unknown")()

            logger.warning(
                "CUDA device not available (is_available={}, device_count={}, torch_cuda={}, cudnn={}, probe_error={}); using CPU",
                has_cuda,
                device_count,
                cuda_version,
                cudnn_version,
                probe_error,
            )
            dev = torch.device("cpu")
    else:
        dev = torch.device(device)
        if dev.type.startswith("cuda") and not has_cuda:
            raise RuntimeError("CUDA requested but not available")

    if dev.type.startswith("cuda") and min_gb is not None:

        try:
            assert_memory(min_gb, dev)
        except RuntimeError as exc:  # pragma: no cover - error path
            logger.warning(f"{exc}. Falling back to CPU")
            dev = torch.device("cpu")
    return dev
