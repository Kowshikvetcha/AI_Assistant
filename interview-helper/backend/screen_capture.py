"""
Screen capture OCR module — extracts text from screenshot images using Tesseract.
"""

import io
import logging
import os
import re
import sys

from PIL import Image
import pytesseract

from config import get_settings

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 5000


def _get_bundled_tesseract_path() -> str | None:
    """Return path to Tesseract bundled alongside the packaged backend, if it exists."""
    # When packaged with PyInstaller the backend exe lives in a folder like:
    #   <install>/resources/backend/main.exe
    # We bundle Tesseract-OCR next to it:
    #   <install>/resources/backend/tesseract/tesseract.exe
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    candidate = os.path.join(base, "tesseract", "tesseract.exe")
    if os.path.isfile(candidate):
        return candidate
    return None


def _configure_tesseract() -> None:
    """Set the Tesseract executable path — checks .env, bundled copy, then PATH."""
    settings = get_settings()

    # 1. Explicit .env override
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        return

    # 2. Bundled copy (packaged app)
    bundled = _get_bundled_tesseract_path()
    if bundled:
        pytesseract.pytesseract.tesseract_cmd = bundled
        return

    # 3. Fall through — pytesseract will try to find it on system PATH


def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Extract text from an image using Tesseract OCR.

    Args:
        image_bytes: Raw image bytes (PNG, JPEG, etc.)

    Returns:
        Extracted and cleaned text, truncated to MAX_TEXT_LENGTH characters.

    Raises:
        RuntimeError: If Tesseract is not installed or image is invalid.
    """
    _configure_tesseract()

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        raise RuntimeError(f"Failed to open image: {e}") from e

    try:
        raw_text = pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError:
        raise RuntimeError(
            "Tesseract is not installed or not found in PATH. "
            "Install from https://github.com/UB-Mannheim/tesseract/wiki "
            "and either add it to PATH or set TESSERACT_CMD in your .env file."
        )
    except Exception as e:
        raise RuntimeError(f"OCR failed: {e}") from e

    # Clean whitespace: collapse multiple blank lines, strip trailing spaces
    text = re.sub(r"[ \t]+\n", "\n", raw_text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
        logger.warning(f"OCR text truncated to {MAX_TEXT_LENGTH} characters")

    return text
