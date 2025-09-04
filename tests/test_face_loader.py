import fakeredis

import routers.visitor as visitor


def _setup_redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    visitor.redis = client
    return client


def test_load_known_faces_wrapper():
    r = _setup_redis()
    r.sadd("face:known_ids", "a", "b")
    r.hset(
        "face:known:a",
        mapping={"name": "Alice", "image": "imgA", "created_at": "100"},
    )
    r.hset(
        "face:known:b",
        mapping={"name": "Bob", "image": "imgB", "created_at": "200"},
    )

    res = visitor._load_known_faces(sort="name")
    assert [f["name"] for f in res] == ["Alice", "Bob"]
    res = visitor._load_known_faces(name="Bob")
    assert [f["id"] for f in res] == ["b"]


def test_load_unregistered_faces_wrapper():
    r = _setup_redis()
    r.sadd("face:unregistered_ids", "u1")
    r.hset(
        "face:unregistered:u1",
        mapping={"name": "Unknown", "image": "imgU", "camera_id": "cam1"},
    )
    res = visitor._load_unregistered_faces(sources=["cam1"])
    assert res == [{"face_id": "u1", "image": "imgU", "name": "Unknown"}]
