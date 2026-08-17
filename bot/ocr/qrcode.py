"""QR code detection.

Two layers: OpenCV's built-in detector first (opencv-python-headless is already
a hard dependency for preprocessing, so this is free), then zbar as a fallback
for anything OpenCV can't resolve — verified against blurred test images to
recover roughly one more tier of blur than OpenCV alone. zbar needs the system
`zbar` library (`brew install zbar` / `apt-get install libzbar0`); if it isn't
installed, the fallback is skipped and OpenCV-only detection still works.
"""

from __future__ import annotations

import logging
import os
import sys

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

if sys.platform == "darwin":
    # Homebrew's zbar isn't on ctypes' default search path on Apple Silicon.
    os.environ.setdefault("DYLD_LIBRARY_PATH", "/opt/homebrew/lib:/usr/local/lib")

try:
    from pyzbar.pyzbar import decode as _zbar_decode
except Exception:  # noqa: BLE001 - pyzbar or its zbar shared library isn't available
    _zbar_decode = None


def _try_cv2(detector: cv2.QRCodeDetector, gray: np.ndarray) -> list[str]:
    ok, decoded, _points, _ = detector.detectAndDecodeMulti(gray)
    return [payload for payload in decoded if payload] if ok else []


def _cv2_variants(gray: np.ndarray):
    """Cheap re-tries for phone photos too blurry for a single detector pass."""
    yield gray

    blurred = cv2.GaussianBlur(gray, (0, 0), 3)
    sharp = cv2.addWeighted(gray, 1.8, blurred, -0.8, 0)
    yield sharp

    upscaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    up_blurred = cv2.GaussianBlur(upscaled, (0, 0), 3)
    up_sharp = cv2.addWeighted(upscaled, 1.8, up_blurred, -0.8, 0)
    yield up_sharp

    _, binary = cv2.threshold(up_sharp, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    yield binary


def _try_zbar(image: Image.Image) -> list[str]:
    if _zbar_decode is None:
        return []
    try:
        return [r.data.decode("utf-8", errors="replace") for r in _zbar_decode(image)]
    except Exception as exc:  # noqa: BLE001
        log.warning("zbar decode failed: %s", exc)
        return []


def decode_qr_codes(image: Image.Image) -> list[str]:
    """Every QR code payload found in the image, in detection order. Tries a few
    sharpened/upscaled OpenCV variants, then zbar, before giving up — real phone
    photos are often too blurry for a single detector pass. Never raises — a QR
    miss must never break the OCR job."""
    try:
        gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        detector = cv2.QRCodeDetector()
        for variant in _cv2_variants(gray):
            found = _try_cv2(detector, variant)
            if found:
                return found
        return _try_zbar(image)
    except Exception as exc:  # noqa: BLE001
        log.warning("qr decode failed: %s", exc)
        return []
