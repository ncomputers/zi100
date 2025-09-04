"""Test profile preferences persistence and timezone effect."""

import os
import time

from config import config as cfg


def test_preferences_persist_and_timezone(client):
    orig_tz = os.environ.get("TZ")
    orig_prefs = cfg.get("preferences", {}).copy()
    orig_cfg_tz = cfg.get("timezone")
    try:
        resp = client.post(
            "/api/profile/preferences",
            json={
                "timezone": "UTC",
                "locale": "en_US",
                "date_format": "%Y-%m-%d",
                "theme": "light",
                "email_alerts": True,
                "language": "en",
            },
        )
        assert resp.json()["saved"]
        assert os.environ.get("TZ") == "UTC"
        assert time.localtime(0).tm_hour == 0
        get_resp = client.get("/api/profile/preferences")
        assert get_resp.json()["preferences"]["timezone"] == "UTC"
        client.post("/api/profile/preferences", json={"timezone": "Asia/Kolkata"})
        assert time.localtime(0).tm_hour == 5
    finally:
        if orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = orig_tz
        try:
            time.tzset()
        except AttributeError:
            pass
        cfg["preferences"] = orig_prefs
        if orig_cfg_tz is None:
            cfg.pop("timezone", None)
        else:
            cfg["timezone"] = orig_cfg_tz
