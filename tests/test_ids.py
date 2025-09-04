from utils.ids import generate_id


def test_generate_id_unique_and_length():
    ids = {generate_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(len(i) == 32 for i in ids)
