import io
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.services.image_preprocess import preprocess_image

_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "labels" / "images"
_REALISTIC = _FIXTURES / "realistic_clean_lager.png"


pytestmark = pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")


@pytest.mark.skipif(not _REALISTIC.is_file(), reason="label fixture image not present")
def test_preprocess_upscale_gives_tesseract_usable_alcohol_line() -> None:
    raw = _REALISTIC.read_bytes()
    preprocessed = preprocess_image(raw)
    assert len(preprocessed) > 0
    ocr_out = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", "6"],
        input=preprocessed,
        capture_output=True,
    ).stdout.decode("utf-8", errors="ignore")
    assert "5.0" in ocr_out


def test_preprocess_passes_through_when_already_large() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (3000, 2000), color=(255, 255, 255)).save(buf, format="PNG")
    large = buf.getvalue()
    assert preprocess_image(large) is large


def test_preprocess_non_image_bytes_unchanged() -> None:
    assert preprocess_image(b"not an image") == b"not an image"
