import json
import sys
from pathlib import Path

import fakeredis
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers.visitor.recognizer import FaceRecognizer


def test_identify_threshold():
    r = fakeredis.FakeRedis()
    cfg = {"features": {"visitor_mgmt": True}, "face_match_thresh": 0.3}
    r.set("known_visitors", json.dumps({"Alice": [0.0, 0.0, 0.0]}))
    recog = FaceRecognizer(cfg, r)
    emb = np.array([0.4, 0.0, 0.0], dtype=np.float32)
    assert recog.identify(emb) is None


def test_duplicate_detection():
    r = fakeredis.FakeRedis()
    cfg = {"features": {"visitor_mgmt": True}, "face_duplicate_thresh": 0.5}
    recog = FaceRecognizer(cfg, r)
    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert not recog.is_duplicate(emb)
    assert recog.is_duplicate(emb)
