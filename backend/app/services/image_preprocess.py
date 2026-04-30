import io

from PIL import Image

# Tesseract often drops very small punctuation (e.g. "5.0" as "50") at typical web/DPI
# scales; upscaling until the long edge reaches this minimum materially improves ABV reads.
_MIN_LONG_EDGE_FOR_OCR = 2800


def preprocess_image(image_bytes: bytes) -> bytes:
    try:
        buffer = io.BytesIO(image_bytes)
        image = Image.open(buffer)
        image.load()
    except OSError:
        return image_bytes

    width, height = image.size
    long_edge = max(width, height)
    if long_edge >= _MIN_LONG_EDGE_FOR_OCR:
        return image_bytes

    scale = _MIN_LONG_EDGE_FOR_OCR / long_edge
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    resampled = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    resampled.save(out, format="PNG", optimize=True)
    return out.getvalue()
