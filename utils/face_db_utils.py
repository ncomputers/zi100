from datetime import datetime
from pathlib import Path
from typing import Any

from modules import face_db
from utils.ids import generate_id
from utils.image import decode_base64_image


def save_base64_to_image(
    base64_string: str, filename_prefix: str = "", subdir: str = ""
) -> str:
    """Decode ``base64_string`` and store it under ``face_db`` directory.

    Parameters
    ----------
    base64_string: str
        The image encoded in base64. It may optionally include a ``data:*``
        prefix which will be stripped before decoding.
    filename_prefix: str, optional
        Prefix added to the generated filename.
    subdir: str, optional
        Sub-directory inside ``face_db`` where the image will be stored.

    Returns
    -------
    str
        The filesystem path to the saved image.
    """
    if "," in base64_string:
        base64_string = base64_string.split(",", 1)[1]
    folder = Path("face_db") / subdir / datetime.now().strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{filename_prefix}_{generate_id()}.jpg"
    file_path = folder / filename
    with open(file_path, "wb") as f:
        f.write(decode_base64_image(base64_string))
    return str(file_path)


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
