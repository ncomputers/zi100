"""Purpose: test visitor_db search."""

import json
import sys
from pathlib import Path

import fakeredis

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import visitor_db


def test_search_visitors_by_name():
    r = fakeredis.FakeRedis()
    visitor_db.init_db(r)
    r.hset("visitor:record:111", mapping={"id": "1", "name": "Alice"})
    r.hset("visitor:record:112", mapping={"id": "2", "name": "Alicia"})
    r.zadd("visitor_name_idx", {"alice|111": 1, "alicia|112": 2})
    r.zadd(
        "vms_logs",
        {
            json.dumps(
                {
                    "ts": 3,
                    "name": "Aliyah",
                    "phone": "113",
                    "visitor_type": "Official",
                    "company_name": "Z",
                }
            ): 3,
        },
    )
    res = visitor_db.search_visitors_by_name("Ali", 5)
    assert {v["name"] for v in res} == {"Alice", "Alicia", "Aliyah"}
