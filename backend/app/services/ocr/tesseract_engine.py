import json
import subprocess
from collections.abc import Callable

from app.services.ocr.ocr_engine import OCREngine


class TesseractEngine(OCREngine):
    def __init__(self, fallback_extractor: Callable[[bytes], str] | None = None) -> None:
        self._fallback_extractor = fallback_extractor or _extract_json_payload

    def extract_text(self, image_bytes: bytes) -> str:
        fallback_text = self._fallback_extractor(image_bytes)
        if fallback_text != "":
            return fallback_text
        return _extract_with_tesseract(image_bytes)


def _extract_json_payload(image_bytes: bytes) -> str:
    try:
        text = image_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return ""

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return text


def _extract_with_tesseract(image_bytes: bytes) -> str:
    command = ["tesseract", "stdin", "stdout", "--psm", "6"]
    result = subprocess.run(command, input=image_bytes, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(result.stderr.decode("utf-8", errors="ignore").strip() or "OCR failed")
    return result.stdout.decode("utf-8", errors="ignore")
