import sys
from pathlib import Path

import fakeredis

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers.visitor.queue import VisitorQueue


def test_queue_push_pop():
    r = fakeredis.FakeRedis()
    q = VisitorQueue(r)
    q.push("1")
    assert q.pop() == "1"
    assert q.pop() is None
