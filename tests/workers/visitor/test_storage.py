import sys
from pathlib import Path

import fakeredis

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers.visitor.storage import VisitorRecord, VisitorStorage


def test_storage_roundtrip():
    r = fakeredis.FakeRedis()
    storage = VisitorStorage(r)
    r.hset("face:raw:1", mapping={"path": "/tmp/x.jpg", "cam_id": "0"})
    raw = storage.get_raw_face("1")
    assert raw["path"] == "/tmp/x.jpg"
    storage.delete_raw_face("1")
    assert storage.get_raw_face("1") == {}
    rec = VisitorRecord(face_id="1", ts=1, cam_id=0, image="img")
    storage.save_visitor(rec)
    assert r.hget("visitor:1", "face_id") == b"1"
