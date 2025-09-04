import pathlib
import sys

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from modules import model_registry


def test_get_yolo_requires_path(monkeypatch):
    monkeypatch.setattr(model_registry, "YOLO", object)
    with pytest.raises(ValueError, match="Model path must be provided"):
        model_registry.get_yolo("")
