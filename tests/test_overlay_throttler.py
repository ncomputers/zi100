from utils.overlay import OverlayThrottler


def test_every_n_and_min_ms():
    ot = OverlayThrottler(every_n=2, min_ms=50)
    assert ot.should_draw(0) is True
    assert ot.should_draw(10) is False  # frame 1 skipped due to every_n
    assert ot.should_draw(60) is True  # frame 2 passes both checks
