from unittest.mock import MagicMock

import psutil

from utils import cpu as cpu_utils


def test_cpu_affinity(monkeypatch):
    cfg = {"cpu_limit_percent": 25}
    fake_process = MagicMock()
    monkeypatch.setattr(psutil, "Process", lambda: fake_process)
    monkeypatch.setattr(cpu_utils.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(cpu_utils.cv2, "setNumThreads", MagicMock())
    if cpu_utils.torch is not None:
        monkeypatch.setattr(cpu_utils.torch, "set_num_threads", MagicMock())
    cpu_utils.apply_thread_limits(cfg)
    expected = max(1, int(8 * 25 / 100))
    fake_process.cpu_affinity.assert_called_once_with(list(range(expected)))
