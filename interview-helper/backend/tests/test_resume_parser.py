"""
Unit tests for resume_parser module.
Tests PDF/TXT extraction, character truncation, and error handling.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from resume_parser import parse_resume, MAX_RESUME_CHARS


def test_parse_txt_resume():
    """Test parsing a plain text resume."""
    resume_text = "John Doe\nSoftware Engineer\n5 years experience in Python"
    file_bytes = resume_text.encode("utf-8")
    result = parse_resume(file_bytes, "resume.txt")
    assert "John Doe" in result
    assert "Software Engineer" in result


def test_parse_txt_resume_strips_whitespace():
    """Test that blank lines are removed."""
    resume_text = "John Doe\n\n\n\nPython Dev\n\n"
    file_bytes = resume_text.encode("utf-8")
    result = parse_resume(file_bytes, "resume.txt")
    assert "\n\n" not in result
    assert "John Doe" in result


def test_parse_resume_truncation():
    """Test that very long resumes are truncated."""
    long_text = "A" * (MAX_RESUME_CHARS + 500)
    file_bytes = long_text.encode("utf-8")
    result = parse_resume(file_bytes, "resume.txt")
    assert len(result) <= MAX_RESUME_CHARS + 50  # Allow for truncation notice
    assert "[... truncated]" in result


def test_parse_resume_unsupported_format():
    """Test that unsupported file types raise ValueError."""
    import pytest

    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_resume(b"some data", "resume.docx")


def test_parse_resume_empty_file():
    """Test that empty files raise ValueError."""
    import pytest

    with pytest.raises(ValueError, match="empty"):
        parse_resume(b"", "resume.txt")


def test_parse_resume_text_extension():
    """Test .text extension works same as .txt."""
    resume_text = "Jane Smith\nData Scientist"
    file_bytes = resume_text.encode("utf-8")
    result = parse_resume(file_bytes, "resume.text")
    assert "Jane Smith" in result
