"""Purpose: Test license module."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.license import generate_license, verify_license


# Test generate and verify
def test_generate_and_verify():
    secret = "default_secret"
    token = generate_license(
        secret,
        days=1,
        max_cameras=2,
        features={
            "in_out_counting": True,
            "visitor_mgmt": True,
            "ppe_detection": True,
            "face_recognition": False,
        },
        client="Test",
    )
    info = verify_license(token)
    assert info["valid"]
    assert info["max_cameras"] == 2
    assert info["client"] == "Test"
