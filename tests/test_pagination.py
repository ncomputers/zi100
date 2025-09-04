from utils.pagination import paginate


def test_paginate_nonpositive_page():
    items = [1, 2, 3, 4]
    assert paginate(items, 0, 2) == [1, 2]
    assert paginate(items, -1, 2) == [1, 2]


def test_paginate_beyond_range():
    items = [1, 2, 3]
    assert paginate(items, 4, 2) == []
