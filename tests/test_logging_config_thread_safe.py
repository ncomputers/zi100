import threading

from logging_config import set_log_level


def test_configure_thread_safe():
    errors = []

    def worker():
        try:
            set_log_level("DEBUG")
        except Exception as exc:  # pragma: no cover - capturing unexpected errors
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
