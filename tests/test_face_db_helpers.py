"""Tests for face_db helper functions."""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import face_db


class Face:
    def __init__(self, embedding: np.ndarray):
        self.embedding = embedding


class IndexStub:
    def __init__(self):
        self.vecs = []

    def add(self, arr):
        self.vecs.extend(arr)

    @property
    def ntotal(self):
        return len(self.vecs)

    def search(self, arr, k):
        if not self.vecs:
            return np.zeros((1, k), dtype="float32"), np.full((1, k), -1)
        mat = np.stack(self.vecs)
        sims = mat @ arr.T
        idx = np.argsort(-sims, axis=0)[:k].T
        D = np.take_along_axis(sims.T, idx, axis=1)
        return D.astype("float32"), idx


def test_detect_single_face_returns_embedding(monkeypatch):
    embedding = np.ones(512, dtype=np.float32)
    monkeypatch.setattr(
        face_db,
        "face_app",
        type("A", (), {"get": lambda self, img: [Face(embedding)]})(),
    )
    rgb = np.zeros((10, 10, 3), dtype=np.uint8)
    emb, face = face_db._detect_single_face(rgb)
    assert emb is not None and face is not None


def test_detect_single_face_invalid(monkeypatch):
    monkeypatch.setattr(
        face_db, "face_app", type("A", (), {"get": lambda self, img: []})()
    )
    rgb = np.zeros((10, 10, 3), dtype=np.uint8)
    emb, face = face_db._detect_single_face(rgb)
    assert emb is None and face is None


def test_check_duplicate_merges(monkeypatch):
    embedding = np.ones(512, dtype=np.float32)
    embedding /= np.linalg.norm(embedding)
    index = IndexStub()
    index.add(embedding.reshape(1, -1))
    monkeypatch.setattr(face_db, "faiss_index", index)
    monkeypatch.setattr(face_db, "id_map", ["v1"])
    called = {}

    def merge_faces(fid, emb):
        called["id"] = fid
        called["emb"] = emb

    monkeypatch.setattr(face_db, "merge_faces", merge_faces)
    matches = face_db._check_duplicate(embedding, True, 0.8)
    assert matches and matches[0]["id"] == "v1"
    assert called["id"] == "v1"


def test_check_duplicate_no_match(monkeypatch):
    embedding = np.ones(512, dtype=np.float32)
    embedding /= np.linalg.norm(embedding)
    index = IndexStub()
    index.add(embedding.reshape(1, -1))
    monkeypatch.setattr(face_db, "faiss_index", index)
    monkeypatch.setattr(face_db, "id_map", ["v1"])
    merged = []
    monkeypatch.setattr(
        face_db, "merge_faces", lambda *args, **kwargs: merged.append(True)
    )
    matches = face_db._check_duplicate(embedding, False, 1.1)
    assert matches == []
    assert merged == []
