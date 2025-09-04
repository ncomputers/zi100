"""License verification and generation helpers without external deps."""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

DEFAULT_SECRET = "default_secret"


# _b64encode routine
def _b64encode(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


# _b64decode routine
def _b64decode(data: bytes) -> bytes:
    padding = b"=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


# generate_license routine
def generate_license(
    secret: str, days: int, max_cameras: int, features: dict, client: str = ""
) -> str:
    """Create a signed license token using HMAC-SHA256."""
    exp = int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())
    payload = {
        "exp": exp,
        "max_cameras": max_cameras,
        "features": features,
        "client": client,
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), payload_json, hashlib.sha256).digest()
    token = _b64encode(payload_json) + b"." + _b64encode(sig)
    return token.decode()


# verify_license routine
def verify_license(license_key: str, secret: str = DEFAULT_SECRET) -> dict:
    """Validate a license token created by :func:`generate_license`."""
    if not license_key:
        return {"valid": False, "error": "Missing license"}
    try:
        payload_b64, sig_b64 = license_key.split(".")
        payload_json = _b64decode(payload_b64.encode())
        expected_sig = hmac.new(secret.encode(), payload_json, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, _b64decode(sig_b64.encode())):
            return {"valid": False, "error": "Invalid signature"}
        payload = json.loads(payload_json.decode())
        if payload.get("exp") and time.time() > payload["exp"]:
            return {"valid": False, "error": "License expired"}
        return {"valid": True, **payload}
    except Exception as e:  # pragma: no cover - unexpected error
        return {"valid": False, "error": str(e)}


__all__ = ["verify_license", "generate_license"]
