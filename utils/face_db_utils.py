from datetime import datetime
from typing import Any

from modules import face_db


def add_face_to_known_db(
    *,
    image_path: str,
    name: str,
    phone: str,
    visitor_type: str,
    gate_pass_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist known face metadata so it appears in the Face DB UI."""
    metadata = metadata or {}
    entry = {
        "name": name,
        "phone": phone,
        "visitor_type": visitor_type,
        "gate_pass_id": gate_pass_id,
        "image_path": image_path,
        "created_at": str(int(datetime.now().timestamp())),
        **metadata,
    }
    if face_db.redis_client:
        face_db.redis_client.hset(f"face:known:{gate_pass_id}", mapping=entry)
        face_db.redis_client.sadd("face:known_ids", gate_pass_id)
        face_db.redis_client.publish("faces_updated", gate_pass_id)
