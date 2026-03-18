"""
Resume parser module.
Extracts plain text from PDF or TXT resume files for LLM context.
"""

import io
import logging

logger = logging.getLogger("interview_helper")

# Max characters to keep from a resume (keeps token usage manageable)
MAX_RESUME_CHARS = 3000


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF file.

    Args:
        file_bytes: Raw bytes of the PDF file.

    Returns:
        Extracted text string.
    """
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n".join(pages)
    except Exception as e:
        logger.error(f"❌ PDF parsing failed: {e}")
        raise ValueError(f"Could not parse PDF: {e}")


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Extract text from a plain text file.

    Args:
        file_bytes: Raw bytes of the text file.

    Returns:
        Decoded text string.
    """
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Try latin-1 as fallback
        return file_bytes.decode("latin-1")


def parse_resume(file_bytes: bytes, filename: str) -> str:
    """Parse a resume file and return clean, truncated text.

    Args:
        file_bytes: Raw bytes of the uploaded file.
        filename: Original filename (used to detect format).

    Returns:
        Cleaned resume text, truncated to MAX_RESUME_CHARS.

    Raises:
        ValueError: If the file type is unsupported or parsing fails.
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext == "pdf":
        raw_text = extract_text_from_pdf(file_bytes)
    elif ext in ("txt", "text"):
        raw_text = extract_text_from_txt(file_bytes)
    else:
        raise ValueError(
            f"Unsupported file type: .{ext}. Please upload a PDF or TXT file."
        )

    # Clean up whitespace
    cleaned = "\n".join(
        line.strip() for line in raw_text.splitlines() if line.strip()
    )

    if not cleaned:
        raise ValueError("Resume file appears to be empty.")

    # Truncate to keep token usage manageable
    if len(cleaned) > MAX_RESUME_CHARS:
        cleaned = cleaned[:MAX_RESUME_CHARS] + "\n[... truncated]"
        logger.info(
            f"📄 Resume truncated to {MAX_RESUME_CHARS} chars "
            f"(original: {len(raw_text)} chars)"
        )

    logger.info(f"📄 Resume parsed: {len(cleaned)} chars from '{filename}'")
    return cleaned
