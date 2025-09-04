import importlib.util
from importlib.machinery import PathFinder
import os
import sys

# Attempt to load real PyTorch if available outside this stub package
_current_dir = os.path.dirname(__file__)


def _is_same_path(a: str, b: str) -> bool:
    """Case-insensitive path comparison that tolerates missing files."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(
            os.path.abspath(b)
        )


_real_spec = None
for path in sys.path:
    # Skip any entry that points to this stub package
    candidate = os.path.join(path, "torch")
    if _is_same_path(candidate, _current_dir):
        continue

    spec = PathFinder.find_spec("torch", [path])
    if spec and spec.origin and not _is_same_path(spec.origin, __file__):
        _real_spec = spec
        break

if _real_spec and _real_spec.origin and not _is_same_path(_real_spec.origin, __file__):
    _real_torch = importlib.util.module_from_spec(_real_spec)
    # Insert the real module early to avoid recursive imports during execution
    sys.modules["torch"] = _real_torch
    assert _real_spec.loader is not None
    _real_spec.loader.exec_module(_real_torch)  # type: ignore[attr-defined]
    # Replace this stub with the real torch module
    sys.modules[__name__] = _real_torch
    globals().update(_real_torch.__dict__)
else:
    class device:
        def __init__(self, name: str):
            self.type = name

        def __str__(self) -> str:
            return self.type

    class _CudaStub:
        def is_available(self) -> bool:
            return False

    cuda = _CudaStub()

    def set_num_threads(n: int) -> None:
        """Stub implementation that ignores requested thread count."""
        return None

