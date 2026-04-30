from typing import Protocol


class OCREngine(Protocol):
    def extract_text(self, image_bytes: bytes) -> str:
        ...
