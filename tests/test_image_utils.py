import base64
import pytest

from utils.image import decode_base64_image


def test_decode_base64_image_valid():
    data = base64.b64encode(b"hello").decode()
    assert decode_base64_image(data) == b"hello"


def test_decode_base64_image_with_prefix():
    prefix_data = "data:image/png;base64," + base64.b64encode(b"world").decode()
    assert decode_base64_image(prefix_data) == b"world"


def test_decode_base64_image_invalid():
    with pytest.raises(ValueError):
        decode_base64_image("not-base64!!!")
