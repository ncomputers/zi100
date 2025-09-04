from __future__ import annotations

import base64
import threading
import time
from typing import Optional

import cv2

from .queue import VisitorQueue
from .recognizer import FaceRecognizer
from .storage import VisitorRecord, VisitorStorage


class VisitorWorker:
    """Orchestrates visitor queue processing."""

    def __init__(self, cfg: dict, redis):
        self.queue = VisitorQueue(redis)
        self.storage = VisitorStorage(redis)
        self.recognizer = FaceRecognizer(cfg, redis)
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._thread is not None:
            self._thread.join(timeout=1)

    def _save_record(self, face_id, img, faces) -> None:
        ok, buf = cv2.imencode(".jpg", img)
        image_b64 = base64.b64encode(buf).decode() if ok else ""
        raw = self.storage.get_raw_face(face_id)
        cam_id = int(raw.get("cam_id", 0)) if raw else 0
        for name in faces:
            record = VisitorRecord(
                face_id=face_id,
                ts=int(time.time()),
                cam_id=cam_id,
                image=image_b64,
                name=name,
            )
            self.storage.save_visitor(record)

    def _process_face_id(self, face_id: str) -> None:
        raw = self.storage.get_raw_face(face_id)
        if not raw:
            return
        path = raw.get("path")
        img = cv2.imread(path) if path else None
        if img is None:
            self.storage.delete_raw_face(face_id)
            return
        faces = []
        for face in self.recognizer.detect(img):
            emb = face.embedding
            if self.recognizer.is_duplicate(emb):
                continue
            name = self.recognizer.identify(emb) or ""
            faces.append(name)
        if faces:
            self._save_record(face_id, img, faces)
        self.storage.delete_raw_face(face_id)

    def run(self) -> None:
        while self.running:
            face_id = self.queue.pop()
            if face_id:
                self._process_face_id(face_id)
            else:
                time.sleep(0.1)
