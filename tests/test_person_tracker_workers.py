import queue
from types import SimpleNamespace

import numpy as np

import modules.tracker.manager as manager_mod
import modules.tracker.stream as stream_mod
from modules.tracker import CaptureWorker, InferWorker, PersonTracker, PostProcessWorker


class DummyCap:
    def __init__(self, tracker, frames, restart=False, fail=False):
        self.tracker = tracker
        self.frames = frames
        self.restart = restart
        self.fail = fail
        self.idx = 0

    def read(self):
        if self.fail:
            return False, None
        if self.idx < len(self.frames):
            frame = self.frames[self.idx]
            self.idx += 1
            if self.restart and self.idx == 1:
                self.tracker.restart_capture = True
            if self.tracker.cfg.get("once"):
                self.tracker.running = False
            return True, frame
        return False, None

    def release(self):
        pass


def make_tracker(monkeypatch, frames, once=True):
    q = queue.Queue(maxsize=2)
    dq = queue.Queue(maxsize=2)
    oq = queue.Queue(maxsize=2)
    tracker = SimpleNamespace(
        cam_id=1,
        src="s",
        src_type="rtsp",
        resolution="640x480",
        rtsp_transport="tcp",
        stream_mode="gstreamer",
        device=SimpleNamespace(type="cpu"),
        cfg={"once": once},
        frame_queue=q,
        det_queue=dq,
        out_queue=oq,
        batch_size=2,
        restart_capture=False,
        debug_stats={},
        running=True,
        tracks={},
        show_ids=False,
        show_track_lines=False,
        show_lines=False,
        line_orientation="vertical",
        line_ratio=0.5,
        show_counts=False,
        in_count=0,
        out_count=0,
        viewers=0,
        output_frame=None,
        preview_scale=1.0,
        _purge_counted=lambda: None,
    )

    def oc(src, cam_id, src_type, resolution, *a, **k):
        assert resolution == "640x480"
        return DummyCap(tracker, frames), "tcp"

    monkeypatch.setattr(stream_mod, "open_capture", oc)
    return tracker


def test_capture_worker_queue(monkeypatch):
    frame = np.zeros((1, 1, 3), dtype=np.uint8)
    tr = make_tracker(monkeypatch, [frame])
    worker = CaptureWorker(tr)
    tr.capture_worker = worker
    worker.run()
    assert not tr.frame_queue.empty()


def test_capture_worker_frame_skip_zero(monkeypatch):
    frames = [np.full((1, 1, 3), i, dtype=np.uint8) for i in range(2)]
    tr = make_tracker(monkeypatch, frames, once=False)
    tr.cfg["frame_skip"] = 0
    worker = CaptureWorker(tr)
    tr.capture_worker = worker
    worker.run()
    assert tr.frame_queue.qsize() == 2
    f1 = tr.frame_queue.get()
    f2 = tr.frame_queue.get()
    assert f1[0, 0, 0] == 0
    assert f2[0, 0, 0] == 1


def test_capture_worker_frame_skip_positive(monkeypatch):
    frames = [np.full((1, 1, 3), i, dtype=np.uint8) for i in range(4)]
    tr = make_tracker(monkeypatch, frames, once=False)
    tr.cfg["frame_skip"] = 2
    worker = CaptureWorker(tr)
    tr.capture_worker = worker
    worker.run()
    assert tr.frame_queue.qsize() == 2
    f1 = tr.frame_queue.get()
    f2 = tr.frame_queue.get()
    assert f1[0, 0, 0] == 0
    assert f2[0, 0, 0] == 2


def test_capture_worker_pipeline_info(monkeypatch):
    frame = np.zeros((1, 1, 3), dtype=np.uint8)
    tr = make_tracker(monkeypatch, [frame])

    def oc(*a, **k):
        cap = DummyCap(tr, [frame])
        cap.pipeline = "ffmpeg -i url"
        return cap, "tcp"

    monkeypatch.setattr(stream_mod, "open_capture", oc)
    worker = CaptureWorker(tr)
    tr.capture_worker = worker
    worker.run()
    assert tr.pipeline_info == "ffmpeg -i url"


def test_capture_worker_sets_backend(monkeypatch):
    frame = np.zeros((1, 1, 3), dtype=np.uint8)
    tr = make_tracker(monkeypatch, [frame])
    worker = CaptureWorker(tr)
    tr.capture_worker = worker
    worker.run()
    assert tr.capture_backend == "DummyCap"


def test_capture_worker_restart(monkeypatch):
    frame = np.zeros((1, 1, 3), dtype=np.uint8)
    q = []

    def oc(*a, **k):
        q.append(1)
        restart = len(q) == 1
        return DummyCap(tr, [frame], restart=restart), "tcp"

    tr = make_tracker(monkeypatch, [frame], once=False)
    monkeypatch.setattr(stream_mod, "open_capture", oc)
    tr.capture_worker = CaptureWorker(tr)

    def stop_after_second(*args, **kwargs):
        if len(q) > 1:
            tr.running = False
        return DummyCap(tr, [frame])

    tr.capture_worker.run()
    assert len(q) >= 2


def test_capture_worker_error(monkeypatch):
    tr = make_tracker(monkeypatch, [], once=False)

    def oc(*a, **k):
        return DummyCap(tr, [], fail=True), "tcp"

    monkeypatch.setattr(stream_mod, "open_capture", oc)
    tr.capture_worker = CaptureWorker(tr)
    tr.capture_worker.run()
    assert not tr.running


def test_capture_worker_error_logging(monkeypatch):
    tr = make_tracker(monkeypatch, [], once=False)

    class ErrCap:
        def __init__(self):
            self.last_status = "error"
            self.last_error = "short read"
            self.pipeline = "ffmpeg -i rtsp://demo"

        def read(self):
            return False, None

        def release(self):
            pass

    monkeypatch.setattr(stream_mod, "open_capture", lambda *a, **k: (ErrCap(), "tcp"))
    logs: list[str] = []
    monkeypatch.setattr(stream_mod.logger, "error", lambda msg: logs.append(msg))

    tr.capture_worker = CaptureWorker(tr)
    tr.capture_worker.run()

    assert any("status=error" in m and "short read" in m for m in logs)


def test_capture_worker_device_update(monkeypatch):
    frame = np.zeros((1, 1, 3), dtype=np.uint8)
    tr = make_tracker(monkeypatch, [frame], once=True)
    worker = CaptureWorker(tr)
    tr.capture_worker = worker
    calls = []

    def oc(*a, **k):
        calls.append(True)
        return DummyCap(tr, [frame]), "tcp"

    monkeypatch.setattr(stream_mod, "open_capture", oc)

    class DummyTorch:
        @staticmethod
        def device(val):
            return SimpleNamespace(type=str(val))

    monkeypatch.setattr(stream_mod, "torch", DummyTorch())
    PersonTracker.update_cfg(tr, {"device": "cpu"})
    tr.restart_capture = True
    worker.run()
    assert len(calls) == 2
    dev = tr.device
    assert getattr(dev, "type", dev) == "cpu"


def test_post_process_worker(monkeypatch):
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    tr = make_tracker(monkeypatch, [frame])
    tr.show_lines = True
    tr.running = False
    tr.det_queue.put((frame, []))
    called = []

    def draw(*a, **k):
        called.append(True)

    monkeypatch.setattr(manager_mod, "draw_overlays", draw)
    worker = PostProcessWorker(tr)
    tr.post_worker = worker
    worker.run()
    assert called and tr.debug_stats.get("last_process_ts") is not None
    assert tr.output_frame.shape == frame.shape
    assert tr.output_frame is not frame
    assert not tr.out_queue.empty()


def test_post_process_worker_error(monkeypatch):
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    tr = make_tracker(monkeypatch, [frame])
    tr.show_lines = True
    tr.running = False
    tr.det_queue.put((frame, []))

    def draw(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(manager_mod, "draw_overlays", draw)
    worker = PostProcessWorker(tr)
    tr.post_worker = worker
    worker.run()
    assert tr.debug_stats.get("last_process_ts") is not None


def test_post_process_worker_face_boxes(monkeypatch):
    frame = np.zeros((30, 30, 3), dtype=np.uint8)
    tr = make_tracker(monkeypatch, [frame])
    tr.show_face_boxes = True
    tr.running = False
    tr.det_queue.put((frame, []))

    class DummyDetector:
        def detect_boxes(self, img):
            return [(5, 5, 20, 20)]

    monkeypatch.setattr(manager_mod, "FaceDetector", lambda: DummyDetector())
    worker = PostProcessWorker(tr)
    tr.post_worker = worker
    worker.run()
    assert tr.output_frame[5, 5].any()


def test_capture_worker_device_update(monkeypatch):
    monkeypatch.setattr(stream_mod, "torch", None)
    frame = np.zeros((1, 1, 3), dtype=np.uint8)
    tr = make_tracker(monkeypatch, [frame], once=False)
    calls: list[bool] = []

    class UpdateCap(DummyCap):
        def read(self):
            if self.idx < len(self.frames):
                frame = self.frames[self.idx]
                self.idx += 1
                if self.idx == 1:
                    PersonTracker.update_cfg(tr, {"device": "cuda"})
                    tr.restart_capture = True
                return True, frame
            return False, None

    def oc(
        src,
        cam_id,
        src_type,
        resolution,
        rtsp_transport,
        stream_mode,
        use_gpu,
        **kwargs,
    ):
        calls.append(use_gpu)
        if len(calls) == 1:
            return UpdateCap(tr, [frame]), "tcp"
        return DummyCap(tr, [], fail=True), "tcp"

    monkeypatch.setattr(stream_mod, "open_capture", oc)
    worker = CaptureWorker(tr)
    tr.capture_worker = worker
    worker.run()
    assert calls == [False, True]


def test_infer_worker(monkeypatch):
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    tr = make_tracker(monkeypatch, [frame])
    tr.running = False
    tr.frame_queue.put(frame)

    class DummyDetector:
        def detect_batch(self, frames, groups):
            assert frames == [frame]
            return [[((0, 0, 1, 1), 0.9, "person")]]

    tr.detector = DummyDetector()
    tr.groups = ["person"]
    worker = InferWorker(tr)
    tr.infer_worker = worker
    worker.run()
    assert not tr.det_queue.empty()
    frm, dets = tr.det_queue.get()
    assert frm is frame
    assert dets == [((0, 0, 1, 1), 0.9, "person")]
