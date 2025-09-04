from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")


def paginate(items: Sequence[T], page: int, limit: int) -> list[T]:
    """Return a slice of items for the given page and limit."""
    if limit <= 0:
        return []
    page = max(page, 1)
    start = (page - 1) * limit
    end = start + limit
    return list(items[start:end])
