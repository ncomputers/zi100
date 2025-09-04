import pytest

from modules.profiler import (
    ProfilerState,
    _collect_stats,
    log_inference,
    register_thread,
)


def test_profiler_state_custom_instance():
    state = ProfilerState()
    register_thread("test-thread", state=state)
    log_inference("test-thread", 0.5, state=state)
    stats = _collect_stats(state)
    assert "test-thread" in stats
    cpu, mem, inf = stats["test-thread"]
    assert inf == pytest.approx(0.5)
    assert cpu >= 0.0
    assert mem > 0
