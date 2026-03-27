"""
Tests for the screen_capture OCR module.
All tests mock pytesseract so Tesseract does not need to be installed.
"""

import io
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from screen_capture import extract_text_from_image, MAX_TEXT_LENGTH


def _make_png_bytes(width: int = 100, height: int = 50) -> bytes:
    """Create a minimal valid PNG image in memory."""
    img = Image.new("RGB", (width, height), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@patch("screen_capture.get_settings")
@patch("screen_capture.pytesseract")
class TestExtractTextFromImage:
    """Tests for extract_text_from_image()."""

    def test_basic_extraction(self, mock_pytesseract, mock_settings):
        mock_settings.return_value = MagicMock(TESSERACT_CMD=None)
        mock_pytesseract.image_to_string.return_value = "Hello World"

        result = extract_text_from_image(_make_png_bytes())
        assert result == "Hello World"
        mock_pytesseract.image_to_string.assert_called_once()

    def test_whitespace_cleaning(self, mock_pytesseract, mock_settings):
        mock_settings.return_value = MagicMock(TESSERACT_CMD=None)
        mock_pytesseract.image_to_string.return_value = (
            "  line one  \n\n\n\n\nline two  \n"
        )

        result = extract_text_from_image(_make_png_bytes())
        assert result == "line one\n\nline two"

    def test_empty_text(self, mock_pytesseract, mock_settings):
        mock_settings.return_value = MagicMock(TESSERACT_CMD=None)
        mock_pytesseract.image_to_string.return_value = "   \n\n  "

        result = extract_text_from_image(_make_png_bytes())
        assert result == ""

    def test_truncation(self, mock_pytesseract, mock_settings):
        mock_settings.return_value = MagicMock(TESSERACT_CMD=None)
        long_text = "A" * (MAX_TEXT_LENGTH + 500)
        mock_pytesseract.image_to_string.return_value = long_text

        result = extract_text_from_image(_make_png_bytes())
        assert len(result) == MAX_TEXT_LENGTH

    def test_tesseract_not_found(self, mock_pytesseract, mock_settings):
        mock_settings.return_value = MagicMock(TESSERACT_CMD=None)
        mock_pytesseract.TesseractNotFoundError = Exception
        mock_pytesseract.image_to_string.side_effect = (
            mock_pytesseract.TesseractNotFoundError("not found")
        )

        with pytest.raises(RuntimeError, match="Tesseract is not installed"):
            extract_text_from_image(_make_png_bytes())

    def test_invalid_image_bytes(self, mock_pytesseract, mock_settings):
        mock_settings.return_value = MagicMock(TESSERACT_CMD=None)

        with pytest.raises(RuntimeError, match="Failed to open image"):
            extract_text_from_image(b"not an image")

    def test_custom_tesseract_path(self, mock_pytesseract, mock_settings):
        mock_settings.return_value = MagicMock(
            TESSERACT_CMD=r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        mock_pytesseract.image_to_string.return_value = "test"
        mock_pytesseract.pytesseract = MagicMock()

        extract_text_from_image(_make_png_bytes())
        assert (
            mock_pytesseract.pytesseract.tesseract_cmd
            == r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )

    def test_ocr_general_error(self, mock_pytesseract, mock_settings):
        mock_settings.return_value = MagicMock(TESSERACT_CMD=None)
        mock_pytesseract.TesseractNotFoundError = type(
            "TesseractNotFoundError", (Exception,), {}
        )
        mock_pytesseract.image_to_string.side_effect = OSError("disk error")

        with pytest.raises(RuntimeError, match="OCR failed"):
            extract_text_from_image(_make_png_bytes())
