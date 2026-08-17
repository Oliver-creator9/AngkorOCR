"""Image cleanup before OCR.

Phone photos are the dominant input and Tesseract is unforgiving of them. Deskewing
and adaptive thresholding typically move accuracy from unusable to good. All of this
is CPU-bound OpenCV work, so callers must run it in a thread.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np
from PIL import Image, ImageOps

log = logging.getLogger(__name__)

MIN_EDGE = 1000      # upscale small crops; Tesseract likes ~300 DPI
MAX_EDGE = 3500      # cap work on 12 MP photos
MAX_SKEW_DEG = 15.0
UNEVEN_LIGHTING = 20.0  # block-mean std above this = shadows/gradient, below = uniform lighting


def _to_cv(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def _to_pil(arr: np.ndarray) -> Image.Image:
    if arr.ndim == 2:
        return Image.fromarray(arr)
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))


def _resize(image: Image.Image) -> Image.Image:
    w, h = image.size
    longest = max(w, h)
    if longest > MAX_EDGE:
        r = MAX_EDGE / longest
    elif longest < MIN_EDGE:
        r = min(MIN_EDGE / longest, 3.0)
    else:
        return image
    return image.resize((max(1, int(w * r)), max(1, int(h * r))), Image.LANCZOS)


def _unevenness(gray: np.ndarray, grid: int = 4) -> float:
    """Std-dev of block-mean brightness across a grid — high means shadows/gradient
    lighting (a real phone photo), low means uniform lighting (a screenshot or scan)."""
    h, w = gray.shape
    means = [
        gray[h * gy // grid : h * (gy + 1) // grid, w * gx // grid : w * (gx + 1) // grid].mean()
        for gy in range(grid)
        for gx in range(grid)
    ]
    return float(np.std(means))


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Rotate to horizontal text lines using the minimum-area box of dark pixels."""
    inverted = cv2.bitwise_not(gray)
    _, mask = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    coords = cv2.findNonZero(mask)
    if coords is None or len(coords) < 50:
        return gray

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle += 90
    elif angle > 45:
        angle -= 90
    if abs(angle) < 0.3 or abs(angle) > MAX_SKEW_DEG:
        return gray

    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def prepare(image: Image.Image, aggressive: bool = True) -> Image.Image:
    """Return an image ready for OCR. Never raises — falls back to the original."""
    try:
        image = ImageOps.exif_transpose(image)  # respect phone rotation metadata
        image = _resize(image)
        if not aggressive:
            return image.convert("L")

        gray = cv2.cvtColor(_to_cv(image), cv2.COLOR_BGR2GRAY)
        gray = _deskew(gray)
        uneven = _unevenness(gray)
        gray = cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7,
                                        searchWindowSize=21)
        # CLAHE handles uneven lighting / shadows across a page far better than a
        # global contrast stretch.
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

        if uneven > UNEVEN_LIGHTING:
            # Shadowed phone photo: a per-block threshold is the only thing that
            # keeps both the lit and shadowed halves of the page readable.
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
            )
        else:
            # Uniformly lit input (screenshot, scan, well-lit photo): a fixed local
            # block size eats fine strokes it doesn't need to. A single global
            # threshold — or Tesseract's own internal binarisation — is gentler and
            # measurably more accurate here.
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        return _to_pil(binary)
    except Exception as exc:  # noqa: BLE001 - preprocessing must never break a job
        log.warning("preprocess failed, using original image: %s", exc)
        return image


def prepare_for_vision(image: Image.Image) -> Image.Image:
    """Vision models prefer the untouched colour image; only fix rotation and size."""
    try:
        return _resize(ImageOps.exif_transpose(image))
    except Exception:  # noqa: BLE001
        return image
