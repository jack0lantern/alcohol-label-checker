from collections.abc import Callable

from app.services.ocr.ocr_engine import OCREngine


class TesseractEngine(OCREngine):
    def __init__(self, fallback_extractor: Callable[[bytes], str] | None = None) -> None:
        self._fallback_extractor = fallback_extractor or _decode_as_text

    def extract_text(self, image_bytes: bytes) -> str:
        return self._fallback_extractor(image_bytes)


def _decode_as_text(image_bytes: bytes) -> str:
    return image_bytes.decode("utf-8")
