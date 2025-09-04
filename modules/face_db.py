"""Helpers for managing persistent visitor face embeddings."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

import cv2
import numpy as np
import psutil
import redis
from loguru import logger

FaceApp = Any  # type: ignore[misc] - InsightFace dependency removed

try:  # optional heavy dependency
    import torch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - torch optional in tests
    torch = None

from config import FACE_THRESHOLDS, config
from utils.gpu import get_device

import types
import numpy as _np


# lightweight FAISS stub since the real dependency is removed
class _StubIndex:
    def __init__(self, dim: int):
        self.dim = dim
        self.vectors: list[_np.ndarray] = []

    @property
    def ntotal(self) -> int:
        return len(self.vectors)

    def add(self, arr: _np.ndarray) -> None:
        self.vectors.extend(arr)

    def search(self, arr: _np.ndarray, k: int):
        if not self.vectors:
            return _np.zeros((1, k), dtype="float32"), _np.full((1, k), -1)
        mat = _np.stack(self.vectors)
        sims = mat @ arr.T
        idx = _np.argsort(-sims, axis=0)[:k].T
        D = _np.take_along_axis(sims.T, idx, axis=1)
        return D.astype("float32"), idx


faiss = types.SimpleNamespace(
    IndexFlatIP=_StubIndex,
    write_index=lambda i, p: None,
    read_index=lambda p: _StubIndex(512),
)


FACES_DIR = Path(__file__).resolve().parent.parent / "public" / "faces"
FACES_DIR.mkdir(parents=True, exist_ok=True)

redis_client: Optional[redis.Redis] = None
face_app: FaceApp | None = None
faiss_index: Optional[faiss.IndexFlatIP] = None
id_map: List[str] = []
model_version: str = ""

# Redis list key for re-embedding jobs
REEMBED_QUEUE = "face:reembed_queue"
CANDIDATE_KEY_PREFIX = "face:unreg:candidates:"


def queue_reembed(face_id: str) -> None:
    """Queue a ``face_id`` for re-embedding."""
    if redis_client is None:
        raise RuntimeError("redis not initialized")
    redis_client.rpush(REEMBED_QUEUE, face_id)


def _load_face_model(cfg: dict) -> FaceApp | None:
    """Return ``None`` since InsightFace support has been removed."""
    logger.debug("Face analysis model unavailable; InsightFace dependency removed")
    return None


def _hydrate_index(r: redis.Redis | None) -> tuple[faiss.IndexFlatIP, list[str]]:
    """Hydrate the FAISS index and id map from Redis."""
    logger.debug("Hydrating FAISS index from Redis")
    index = faiss.IndexFlatIP(512)
    ids: list[str] = []
    if r is None:
        logger.warning("Redis client not provided; starting with empty index")
        return index, ids
    try:
        raw_ids = r.lrange("face:id_map", 0, -1)
        if not raw_ids:
            known_ids = sorted(r.smembers("face:known_ids"))
            if known_ids:
                ids_str = [i.decode() if isinstance(i, bytes) else i for i in known_ids]
                r.rpush("face:id_map", *ids_str)
                raw_ids = ids_str
        for rid in raw_ids:
            fid = rid.decode() if isinstance(rid, bytes) else rid
            emb = r.hget(f"face:known:{fid}", "embedding")
            if not emb:
                continue
            if isinstance(emb, bytes):
                emb = emb.decode()
            try:
                vec = np.array(json.loads(emb), dtype="float32")
                index.add(vec.reshape(1, -1))
                ids.append(fid)
            except Exception:
                logger.exception(f"Failed to parse embedding for {fid}")
        logger.debug(f"Hydrated FAISS index with {index.ntotal} entries")
    except Exception:
        logger.exception("Failed to hydrate FAISS index from Redis")
    return index, ids


def init(cfg: dict, r: redis.Redis) -> None:
    """Initialize shared objects and FAISS index."""
    global redis_client, face_app, faiss_index, id_map, model_version
    redis_client = r
    model_version = cfg.get("visitor_model", "")
    config["model_version"] = model_version

    if not cfg.get("enable_face_recognition", True):
        logger.info("Face recognition disabled via configuration")
        face_app = None
        faiss_index = None
        id_map = []
        return

    face_app = _load_face_model(cfg)
    faiss_index, id_map = _hydrate_index(redis_client)


# _decode_image routine
def _decode_image(image_bytes: bytes) -> np.ndarray | None:
    """Return an RGB image array from ``image_bytes`` or ``None``."""
    arr = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return None
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


# _detect_single_face routine
def _detect_single_face(rgb_img: np.ndarray) -> tuple[np.ndarray | None, Any | None]:
    """Return embedding and face when exactly one face is detected."""
    if face_app is None:
        return None, None
    faces = face_app.get(rgb_img)
    if len(faces) != 1:
        return None, None
    face = faces[0]
    emb = getattr(face, "embedding", None)
    if emb is None:
        return None, None
    return emb.astype(np.float32), face


# _check_duplicate routine
def _check_duplicate(
    embedding: np.ndarray,
    merge_on_match: bool,
    threshold: float,
) -> list[dict]:
    """Search for duplicate embeddings and merge when configured."""
    matches = search_embedding(embedding, 1, threshold)
    if matches:
        match_id = matches[0]["id"].split(":", 1)[-1]
        if merge_on_match:
            merge_faces(match_id, embedding)
    return matches


# _prepare_face routine
def _prepare_face(
    image_bytes: bytes,
    *,
    merge_on_match: bool = False,
    threshold: float = FACE_THRESHOLDS.db_duplicate,
    single_face_msg: str = "Please upload a single-face image",
) -> tuple[Optional[np.ndarray], Optional[Any], Optional[np.ndarray], list[dict]]:
    """Return embedding, face, image array and duplicates if any.

    ``single_face_msg`` is raised as :class:`ValueError` when the image does
    not contain exactly one face.
    """
    if not redis_client or face_app is None:
        msg = "Face DB not initialized or feature disabled"
        logger.warning(msg)
        raise ValueError(msg)
    rgb = _decode_image(image_bytes)
    if rgb is None:
        return None, None, None, []
    emb, face = _detect_single_face(rgb)
    if emb is None or face is None:
        raise ValueError(single_face_msg)
    if not np.any(emb):
        return None, None, None, []
    emb /= max(np.linalg.norm(emb), 1e-6)
    matches = _check_duplicate(emb, merge_on_match, threshold)
    if matches:
        return None, None, None, matches
    return emb, face, rgb, []


# add_face routine
def add_face(
    visitor_id: str,
    image_bytes: bytes,
    camera_id: str | None = None,
    device_id: str | None = None,
    source_platform: str | None = None,
    *,
    merge_on_match: bool = False,
    threshold: float = FACE_THRESHOLDS.db_duplicate,
) -> tuple[bool, list[dict]]:
    """Detect a single face and store its embedding under ``visitor_id``.

    Duplicate detection runs against the current database and if a match is
    found above ``threshold`` the insertion is skipped.  When
    ``merge_on_match`` is ``True`` the new embedding is merged into the
    existing record and the call is treated as successful.
    """
    emb, face, rgb, matches = _prepare_face(
        image_bytes,
        merge_on_match=merge_on_match,
        threshold=threshold,
        single_face_msg="Please upload a single-face image",
    )
    if emb is None or face is None or rgb is None:
        return bool(matches) and merge_on_match, matches
    x1, y1, x2, y2 = [int(v) for v in face.bbox]
    crop = rgb[y1:y2, x1:x2]
    path = FACES_DIR / f"{visitor_id}.jpg"
    cv2.imwrite(str(path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
    # Store embedding information in a Redis hash keyed by ``face_db`` for
    # backwards compatibility with existing integrations and unit tests.
    # Each field is the visitor identifier mapped to a JSON payload.
    redis_client.hset(
        "face_db",
        visitor_id,
        json.dumps(
            {
                "embedding": emb.tolist(),
                "image_path": str(path),
                "model_version": config.get("model_version", ""),
            }
        ),
    )
    # maintain convenient lookup of known face ids
    existing_name = redis_client.hget(f"face:known:{visitor_id}", "name")
    if isinstance(existing_name, bytes):
        existing_name = existing_name.decode()
    mapping = {
        "name": existing_name or visitor_id,
        "embedding": json.dumps(emb.tolist()),
        "image_path": str(path),
        "created_at": str(int(time.time())),
        "model_version": str(config.get("model_version", "")),
    }
    if camera_id:
        mapping["camera_id"] = camera_id
    if device_id:
        mapping["device_id"] = device_id
    if source_platform:
        mapping["source_platform"] = source_platform
    redis_client.hset(f"face:known:{visitor_id}", mapping=mapping)
    redis_client.sadd("face:known_ids", visitor_id)
    redis_client.publish("faces_updated", visitor_id)
    if faiss_index is not None:
        faiss_index.add(emb.reshape(1, -1))
        id_map.append(visitor_id)
        if redis_client:
            redis_client.rpush("face:id_map", visitor_id)
    return True, []


# add_face_if_single_detected routine
def add_face_if_single_detected(
    image_bytes: bytes,
    person_id: str,
    *,
    merge_on_match: bool = False,
    threshold: float = FACE_THRESHOLDS.db_duplicate,
) -> bool:
    """Wrapper used by API endpoints to safely add a face if exactly one is detected."""
    try:
        ok, _ = add_face(
            person_id,
            image_bytes,
            merge_on_match=merge_on_match,
            threshold=threshold,
        )
        return ok
    except ValueError:
        return False


# insert routine
def insert(
    image_bytes: bytes,
    person_id: str,
    source: str = "gatepass",
    camera_id: str | None = None,
    device_id: str | None = None,
    source_platform: str | None = None,
    *,
    merge_on_match: bool = False,
    threshold: float = FACE_THRESHOLDS.db_duplicate,
) -> tuple[bool, list[dict]]:
    """Insert a face embedding without quality checks.

    Raises ``ValueError`` if the image does not contain exactly one face.

    Parameters
    ----------
    image_bytes: bytes
        Raw image bytes containing a visitor face.
    person_id: str
        Identifier (typically gate pass ID) used to store the face.
    source: str, optional
        Namespace prefix so manual/gatepass images are kept separate from
        real-time stream captures. Defaults to ``gatepass``.
    camera_id, device_id, source_platform: str, optional
        Additional metadata describing where the face was captured.
    """
    emb, face, rgb, matches = _prepare_face(
        image_bytes,
        merge_on_match=merge_on_match,
        threshold=threshold,
        single_face_msg="Exactly one face required",
    )
    if emb is None or face is None or rgb is None:
        return bool(matches) and merge_on_match, matches
    # Save only the detected face region rather than the entire frame
    x1, y1, x2, y2 = [int(v) for v in face.bbox]
    crop = rgb[y1:y2, x1:x2]
    path = FACES_DIR / f"{source}_{person_id}.jpg"
    cv2.imwrite(str(path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
    redis_client.hset(
        f"face_db:{source}:{person_id}",
        mapping={
            "embedding": json.dumps(emb.tolist()),
            "image_path": str(path),
            "model_version": config.get("model_version", ""),
        },
    )
    existing_name = redis_client.hget(f"face:known:{person_id}", "name")
    if isinstance(existing_name, bytes):
        existing_name = existing_name.decode()
    mapping = {
        "name": existing_name or person_id,
        "embedding": json.dumps(emb.tolist()),
        "image_path": str(path),
        "created_at": str(int(time.time())),
        "source": source,
        "model_version": str(config.get("model_version", "")),
    }
    if camera_id:
        mapping["camera_id"] = camera_id
    if device_id:
        mapping["device_id"] = device_id
    if source_platform:
        mapping["source_platform"] = source_platform
    redis_client.hset(f"face:known:{person_id}", mapping=mapping)
    redis_client.sadd("face:known_ids", person_id)
    redis_client.publish("faces_updated", person_id)
    if faiss_index is not None:
        faiss_index.add(emb.reshape(1, -1))
        fid = f"{source}:{person_id}"
        id_map.append(fid)
        if redis_client:
            redis_client.rpush("face:id_map", fid)
    return True, []


# delete_face routine
def delete_face(person_id: str) -> None:
    """Remove a face embedding and update the known IDs set."""
    if not redis_client:
        return
    redis_client.hdel("face_db", person_id)
    redis_client.delete(f"face:known:{person_id}")
    redis_client.srem("face:known_ids", person_id)


# remove_from_index routine
def remove_from_index(face_id: str) -> None:
    """Remove ``face_id`` from the FAISS index and persist state."""
    global faiss_index, id_map
    if faiss_index is None:
        return
    # drop any entries whose suffix matches ``face_id``
    new_map = [fid for fid in id_map if fid.split(":", 1)[-1] != face_id]
    if len(new_map) == len(id_map):
        return  # nothing to do
    id_map = new_map
    if redis_client:
        redis_client.delete("face:id_map")
        if id_map:
            redis_client.rpush("face:id_map", *id_map)
    dim = getattr(faiss_index, "d", getattr(faiss_index, "dim", 512))
    faiss_index = faiss.IndexFlatIP(dim)
    if redis_client and id_map:
        vectors = []
        for fid in id_map:
            lookup_id = fid.split(":", 1)[-1]
            emb = redis_client.hget(f"face:known:{lookup_id}", "embedding")
            if emb:
                if isinstance(emb, bytes):
                    emb = emb.decode()
                try:
                    vec = np.array(json.loads(emb), dtype="float32")
                    vectors.append(vec)
                except Exception:
                    pass
        if vectors:
            faiss_index.add(np.vstack(vectors))


# add_to_index routine
def add_to_index(face_id: str, embedding: np.ndarray) -> None:
    """Add ``embedding`` for ``face_id`` to the FAISS index and persist."""
    global faiss_index, id_map
    if faiss_index is None:
        return
    emb = embedding.astype("float32")
    if emb.ndim == 1:
        emb = emb.reshape(1, -1)
    faiss_index.add(emb)
    id_map.append(face_id)
    if redis_client:
        redis_client.rpush("face:id_map", face_id)


# search_embedding routine
def search_embedding(
    embedding: np.ndarray, top_k: int = 5, threshold: float | None = None
) -> list[dict]:
    """Search the FAISS index directly using an embedding."""
    if faiss_index is None or faiss_index.ntotal == 0:
        return []
    emb = embedding.astype("float32")
    if emb.ndim == 1:
        emb = emb.reshape(1, -1)
    emb /= max(np.linalg.norm(emb), 1e-6)
    D, I = faiss_index.search(emb, top_k)
    results: list[dict] = []
    for score, idx in zip(D[0], I[0]):
        if idx < 0 or idx >= len(id_map):
            continue
        if threshold is not None and score < threshold:
            continue
        results.append({"id": id_map[idx], "score": float(score)})
    return results


def cache_unregistered_candidates(
    face_id: str, embedding: np.ndarray, top_k: int = 5
) -> list[dict]:
    """Precompute similarity candidates for an unregistered face."""
    if redis_client is None:
        return []
    matches = [
        m
        for m in search_embedding(embedding, top_k + 1)
        if m["id"].split(":", 1)[-1] != face_id
    ]
    key = f"{CANDIDATE_KEY_PREFIX}{face_id}"
    redis_client.delete(key)
    if matches:
        redis_client.rpush(key, *(json.dumps(m) for m in matches))
    return matches


def get_top_matches(face_id: str, threshold: float, top_k: int = 5) -> list[dict]:
    """Return cached similarity candidates above ``threshold`` for API use."""
    if redis_client is None:
        return []
    key = f"{CANDIDATE_KEY_PREFIX}{face_id}"
    raw = redis_client.lrange(key, 0, -1)
    if not raw:
        emb_json = redis_client.hget(f"face:known:{face_id}", "embedding")
        if not emb_json:
            return []
        if isinstance(emb_json, bytes):
            emb_json = emb_json.decode()
        try:
            emb = np.array(json.loads(emb_json), dtype="float32")
        except Exception:
            return []
        cache_unregistered_candidates(face_id, emb, top_k)
        raw = redis_client.lrange(key, 0, -1)
    results: list[dict] = []
    for r in raw:
        if isinstance(r, bytes):
            r = r.decode()
        try:
            m = json.loads(r)
        except Exception:
            continue
        if m.get("score", 0) >= threshold:
            results.append(m)
    return results[:top_k]


# search_faces routine
def search_faces(
    image_bytes: bytes, top_k: int = 5, threshold: float | None = None
) -> list[dict]:
    """Return top-k matches from FAISS with cosine similarity.

    Parameters
    ----------
    image_bytes:
        Raw image data containing a face to match against the database.
    top_k:
        Number of results to return.
    threshold:
        Optional minimum similarity score required for a match to be
        included in the results.
    """
    if not face_app or faiss_index is None or faiss_index.ntotal == 0:
        return []
    arr = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return []
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    faces = face_app.get(rgb)
    if not faces:
        return []
    emb = faces[0].embedding.astype(np.float32)
    if not np.any(emb):
        return []
    emb /= max(np.linalg.norm(emb), 1e-6)
    D, I = faiss_index.search(emb.reshape(1, -1), top_k)
    results = []
    for score, idx in zip(D[0], I[0]):
        if idx < 0 or idx >= len(id_map):
            continue
        if threshold is not None and score < threshold:
            continue
        results.append({"id": id_map[idx], "score": float(score)})
    return results


# merge_faces routine
def merge_faces(existing_id: str, new_embedding: np.ndarray) -> None:
    """Average ``new_embedding`` into ``existing_id`` and update the index."""
    if not redis_client:
        return
    rec = redis_client.hget(f"face:known:{existing_id}", "embedding")
    if rec:
        if isinstance(rec, bytes):
            rec = rec.decode()
        try:
            old = np.array(json.loads(rec), dtype="float32")
        except Exception:
            old = new_embedding
    else:
        old = new_embedding
    avg = (old + new_embedding) / 2.0
    avg /= max(np.linalg.norm(avg), 1e-6)
    redis_client.hset(
        f"face:known:{existing_id}",
        mapping={
            "embedding": json.dumps(avg.tolist()),
            "model_version": str(config.get("model_version", "")),
        },
    )
    remove_from_index(existing_id)
    add_to_index(existing_id, avg)


# reembed_face routine
def reembed_face(face_id: str) -> None:
    """Recompute embedding for ``face_id`` with the current model version."""
    if not redis_client or face_app is None:
        raise ValueError("Face DB not initialized")
    path = redis_client.hget(f"face:known:{face_id}", "image_path")
    if not path:
        raise ValueError("image_path_missing")
    if isinstance(path, bytes):
        path = path.decode()
    img = cv2.imread(path)
    if img is None:
        raise ValueError("image_not_found")
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    faces = face_app.get(rgb)
    if len(faces) != 1:
        raise ValueError("Exactly one face required")
    emb = faces[0].embedding.astype(np.float32)
    if not np.any(emb):
        raise ValueError("empty_embedding")
    emb /= max(np.linalg.norm(emb), 1e-6)
    redis_client.hset(
        f"face:known:{face_id}",
        mapping={
            "embedding": json.dumps(emb.tolist()),
            "model_version": str(config.get("model_version", "")),
            "updated_at": str(int(time.time())),
        },
    )
    remove_from_index(face_id)
    add_to_index(face_id, emb)
    redis_client.publish("faces_updated", face_id)
