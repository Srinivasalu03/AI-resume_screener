"""
PDF Text Extraction Service

Extracts text content from PDF files using a dual-method approach:
  1. PyPDF2 (faster) as the primary extractor
  2. pdfplumber (more accurate for complex layouts) as fallback
"""

import logging
import re
from pathlib import Path

import PyPDF2
import pdfplumber

logger = logging.getLogger(__name__)

# Minimum characters to consider an extraction successful
_MIN_TEXT_LENGTH = 50


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract text from a PDF file.

    Tries PyPDF2 first (faster), then falls back to pdfplumber (handles
    complex layouts better).  Raises if both methods fail or yield too
    little text.
    """
    # Method 1: PyPDF2
    try:
        text = _extract_with_pypdf2(pdf_path)
        if text and len(text.strip()) >= _MIN_TEXT_LENGTH:
            return text
    except Exception as e:
        logger.warning("PyPDF2 extraction failed: %s", e)

    # Method 2: pdfplumber fallback
    try:
        text = _extract_with_pdfplumber(pdf_path)
        if text and len(text.strip()) >= _MIN_TEXT_LENGTH:
            return text
    except Exception as e:
        logger.warning("pdfplumber extraction failed: %s", e)
        raise RuntimeError("Failed to extract text from PDF using both methods") from e

    raise RuntimeError("PDF appears to be empty or contains only images")


def _extract_with_pypdf2(pdf_path: Path) -> str:
    """Extract text using PyPDF2."""
    parts = []
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)
    return "\n".join(parts).strip()


def _extract_with_pdfplumber(pdf_path: Path) -> str:
    """Extract text using pdfplumber (better for complex layouts)."""
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)
    return "\n".join(parts).strip()


def clean_text(text: str) -> str:
    """
    Normalize text for NLP analysis.

    Steps: lowercase → remove emails → remove URLs → strip special
    characters → collapse whitespace → drop very short tokens.
    """
    text = text.lower()
    text = re.sub(r"\S+@\S+", "", text)             # emails
    text = re.sub(r"http\S+|www\S+", "", text)       # URLs
    text = re.sub(r"[^a-z0-9\s]", " ", text)         # special chars
    text = re.sub(r"\s+", " ", text)                  # whitespace
    words = [w for w in text.split() if len(w) >= 2]  # short tokens
    return " ".join(words).strip()
