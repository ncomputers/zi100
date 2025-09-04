import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import fakeredis
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers.visitor import VisitorWorker


def test_worker_filters_duplicates(tmp_path):
    r = fakeredis.FakeRedis()
    cfg = {
        "features": {"visitor_mgmt": True},
        "face_duplicate_thresh": 0.5,
    }
    worker = VisitorWorker(cfg, r)

    img = np.zeros((120, 120, 3), dtype=np.uint8)
    import types

    import workers.visitor as vw_module

    dummy_cv2 = types.SimpleNamespace(
        imread=lambda p: img,
        imencode=lambda ext, crop: (True, b"0"),
        cvtColor=lambda i, c: i,
        COLOR_BGR2GRAY=0,
        CV_64F=0,
        Laplacian=lambda i, d: np.zeros((1, 1), dtype=np.float32),
    )
    vw_module.cv2 = dummy_cv2

    class Face:
        embedding = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        bbox = [0, 0, 100, 100]
        det_score = 0.99

    class App:
        def get(self, img):
            return [Face]

    worker.recognizer.app = App()

    from PIL import Image

    for i in range(2):
        path = tmp_path / f"f{i}.jpg"
        Image.fromarray(img).save(path)
        r.hset(f"face:raw:{i}", mapping={"path": str(path), "cam_id": 0})
        r.rpush("visitor_queue", str(i))
    worker.running = True
    t = __import__("threading").Thread(target=worker.run, daemon=True)
    t.start()
    __import__("time").sleep(1)
    worker.stop()
    t.join()
    assert len(list(r.scan_iter("visitor:*"))) == 1
    assert r.hlen("face:raw:0") == 0 and r.hlen("face:raw:1") == 0


def test_run_invokes_process_face_id():
    redis = MagicMock()
    redis.get.return_value = None
    worker = VisitorWorker({}, redis)
    worker.queue = MagicMock()
    worker.queue.pop.return_value = "fid"

    def stop_after(_):
        worker.running = False

    worker._process_face_id = MagicMock(side_effect=stop_after)
    worker.running = True
    worker.run()
    worker._process_face_id.assert_called_once_with("fid")
    worker.queue.pop.assert_called_once()


def test_process_face_id_invokes_save_record():
    redis = MagicMock()
    redis.get.return_value = None
    worker = VisitorWorker({}, redis)
    worker.storage = MagicMock()
    worker.recognizer = MagicMock()
    img = np.zeros((1, 1, 3), dtype=np.uint8)
    worker.storage.get_raw_face.return_value = {"path": "p", "cam_id": "1"}
    face = MagicMock()
    face.embedding = np.array([0, 0, 0])
    worker.recognizer.detect.return_value = [face]
    worker.recognizer.is_duplicate.return_value = False
    worker.recognizer.identify.return_value = "name"
    worker._save_record = MagicMock()
    with patch("workers.visitor.cv2.imread", return_value=img):
        worker._process_face_id("fid")
    worker._save_record.assert_called_once_with("fid", img, ["name"])
    worker.storage.delete_raw_face.assert_called_once_with("fid")


def test_save_record_persists_each_face():
    redis = MagicMock()
    redis.get.return_value = None
    worker = VisitorWorker({}, redis)
    worker.storage = MagicMock()
    img = np.zeros((1, 1, 3), dtype=np.uint8)
    worker.storage.get_raw_face.return_value = {"cam_id": "2"}
    with patch("workers.visitor.cv2.imencode", return_value=(True, b"0")):
        worker._save_record("f", img, ["a", "b"])
    assert worker.storage.save_visitor.call_count == 2
