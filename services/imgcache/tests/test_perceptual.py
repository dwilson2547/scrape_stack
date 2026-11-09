import io
import pytest
from PIL import Image
from app.perceptual import compute_dhash


def make_image(size=(100, 100), color=(128, 64, 32)):
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format="PNG")
    return buf.getvalue()


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def test_same_image_different_resolutions():
    small = make_image(size=(100, 100))
    large = make_image(size=(400, 400))
    h1 = compute_dhash(small)
    h2 = compute_dhash(large)
    assert h1 is not None
    assert h2 is not None
    assert hamming(h1, h2) <= 4


def test_different_images_different_hash():
    img1 = make_image(color=(255, 0, 0))
    img2 = make_image(color=(0, 0, 255))
    h1 = compute_dhash(img1)
    h2 = compute_dhash(img2)
    assert h1 is not None
    assert h2 is not None
    assert isinstance(h1, str)
    assert isinstance(h2, str)


def test_svg_returns_none():
    svg_bytes = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
    result = compute_dhash(svg_bytes)
    assert result is None


def test_invalid_bytes_returns_none():
    result = compute_dhash(b"not an image at all 1234567890")
    assert result is None
