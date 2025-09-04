import json
import sys
from pathlib import Path

import fakeredis
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import set_config
from utils.face_db_utils import add_face_to_known_db


def test_add_face_and_worker():
    r = fakeredis.FakeRedis()
    cfg = {
        "features": {"visitor_mgmt": True, "face_recognition": True},
        "visitor_model": "buffalo_l",
    }
    set_config(cfg)
    from modules import face_db

    face_db.redis_client = r
    fid = "1" * 32
    emb = np.zeros(512, dtype=np.float32)
    r.hset(f"face:known:{fid}", mapping={"embedding": json.dumps(emb.tolist())})
    pubsub = r.pubsub()
    pubsub.subscribe("faces_updated")
    pubsub.get_message()
    add_face_to_known_db(
        image_path="/tmp/a.jpg",
        name="Alice",
        phone="123",
        visitor_type="staff",
        gate_pass_id=fid,
    )
    msg = pubsub.get_message(timeout=1)
    assert (
        msg
        and (msg["data"].decode() if isinstance(msg["data"], bytes) else msg["data"])
        == fid
    )
    fields = {k.decode(): v.decode() for k, v in r.hgetall(f"face:known:{fid}").items()}
    assert fields["name"] == "Alice"
    assert fid.encode() in r.smembers("face:known_ids")
