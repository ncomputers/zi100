import fakeredis
from routers import visitor
from routers.visitor.face_loader import load_faces


def setup_env():
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis()
    visitor.init_context(cfg, r, ".", [])
    return r


def test_load_faces_cursor_and_filters(tmp_path):
    r = setup_env()
    faces = {
        "1": {
            "name": "Alice",
            "email": "a@example.com",
            "phone": "111",
            "visitor_id": "v1",
            "camera_id": "cam1",
            "last_seen_at": "100",
            "image_b64": "img1",
        },
        "2": {
            "name": "Bob",
            "email": "b@example.com",
            "phone": "222",
            "visitor_id": "v2",
            "camera_id": "cam2",
            "last_seen_at": "90",
            "image_b64": "img2",
        },
        "3": {
            "name": "Carol",
            "email": "c@example.com",
            "phone": "333",
            "visitor_id": "v3",
            "camera_id": "cam1",
            "last_seen_at": "80",
            "image_b64": "img3",
        },
    }
    for fid, mapping in faces.items():
        r.hset(f"face:known:{fid}", mapping=mapping)
        r.zadd("face:known_ids", {fid: int(mapping["last_seen_at"])})

    fields_map = {
        "prefix": "face:known:",
        "fields": {
            "id": lambda fid, f, ts, d, img: fid,
            "name": lambda fid, f, ts, d, img: f.get("name", ""),
            "image": lambda fid, f, ts, d, img: img,
            "camera_id": lambda fid, f, ts, d, img: f.get("camera_id", ""),
            "last_seen": lambda fid, f, ts, d, img: ts,
        },
    }

    batch, cursor = load_faces("face:known_ids", fields_map, limit=2)
    assert [f["id"] for f in batch] == ["1", "2"]
    assert cursor == 90

    batch2, cursor2 = load_faces("face:known_ids", fields_map, limit=2, cursor=cursor)
    assert [f["id"] for f in batch2] == ["3"]
    assert cursor2 is None

    batch3, _ = load_faces("face:known_ids", fields_map, limit=2, q="bob")
    assert [f["id"] for f in batch3] == ["2"]

    batch4, _ = load_faces("face:known_ids", fields_map, limit=2, camera_id="cam1")
    assert [f["id"] for f in batch4] == ["1", "3"]
