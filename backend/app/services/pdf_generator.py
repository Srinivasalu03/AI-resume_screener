"""
PDF Generation Service

Generates clean, professional PDF documents from resume text using fpdf2.
Supports both structured (section-based) and unstructured resume layouts.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Optional

from fpdf import FPDF

logger = logging.getLogger(__name__)

# Section headers to render with special formatting
SECTION_HEADERS = {
    "summary", "experience", "skills", "education", "projects",
}


class ResumePDF(FPDF):
    """Custom FPDF subclass for resume generation."""

    def header(self):
        pass  # No automatic header

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def generate_resume_pdf(
    resume_text: str,
    sections: Optional[Dict[str, str]] = None,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Generate a formatted PDF resume.

    If sections dict is provided, renders with proper section headers.
    Otherwise, renders the raw resume_text with basic formatting.

    Returns the output file path.
    """
    if output_path is None:
        raise ValueError("output_path is required")

    pdf = ResumePDF()
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    if sections and len(sections) > 1:
        _render_structured(pdf, sections)
    else:
        _render_plain(pdf, resume_text)

    pdf.output(str(output_path))
    logger.info("Generated PDF: %s", output_path)
    return output_path


def _render_structured(pdf: ResumePDF, sections: Dict[str, str]) -> None:
    """Render a resume with detected sections, using formatted headers."""
    section_order = ["header", "summary", "skills", "experience", "projects", "education"]
    rendered = set()

    for section_name in section_order:
        if section_name in sections:
            _render_section(pdf, section_name, sections[section_name])
            rendered.add(section_name)

    # Render any remaining sections
    for section_name, content in sections.items():
        if section_name not in rendered and section_name != "unstructured":
            _render_section(pdf, section_name, content)


def _render_section(pdf: ResumePDF, name: str, content: str) -> None:
    """Render a single section with appropriate formatting."""
    lines = content.split("\n")

    if name == "header":
        # Header section: render first non-empty line as name, rest as contact info
        first_rendered = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if not first_rendered:
                # Name line - large and bold
                pdf.set_font("Helvetica", "B", 16)
                pdf.set_text_color(30, 30, 30)
                pdf.multi_cell(0, 10, _safe_text(stripped), new_x="LMARGIN", new_y="NEXT")
                first_rendered = True
            else:
                # Contact info
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, 5, _safe_text(stripped), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        return

    # Section header
    if name in SECTION_HEADERS:
        pdf.ln(3)
        _add_section_header(pdf, name.replace("_", " ").title())

    # Section body (skip the first line if it matches the section header pattern)
    body_lines = list(lines)
    if body_lines:
        first_clean = re.sub(r"[:\-_|#*=]+", "", body_lines[0].strip()).strip()
        if len(first_clean) < 40:
            body_lines = body_lines[1:]

    _render_lines(pdf, body_lines)
    pdf.ln(2)


def _render_lines(pdf: ResumePDF, lines: list) -> None:
    """Render a list of text lines, handling bullets."""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            pdf.ln(2)
            continue

        # Detect bullet points
        if re.match(r"^[-*\u2022]\s+", stripped):
            bullet_content = re.sub(r"^[-*\u2022]\s+", "", stripped)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 5, "   - " + _safe_text(bullet_content), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 5, _safe_text(stripped), new_x="LMARGIN", new_y="NEXT")


def _add_section_header(pdf: ResumePDF, title: str) -> None:
    """Add a bold section header with a horizontal rule."""
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 30, 100)
    pdf.multi_cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    # Draw a thin line under the header
    pdf.set_draw_color(30, 30, 100)
    pdf.set_line_width(0.3)
    y = pdf.get_y()
    pdf.line(20, y, pdf.w - 20, y)
    pdf.ln(3)


def _render_plain(pdf: ResumePDF, text: str) -> None:
    """Render raw resume text with basic formatting."""
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(50, 50, 50)

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            pdf.ln(3)
            continue

        # Detect potential headers (short, possibly uppercase)
        if len(stripped) < 40 and stripped == stripped.upper() and len(stripped) > 2:
            _add_section_header(pdf, stripped.title())
        elif re.match(r"^[-*\u2022]\s+", stripped):
            bullet_content = re.sub(r"^[-*\u2022]\s+", "", stripped)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 5, "   - " + _safe_text(bullet_content), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 5, _safe_text(stripped), new_x="LMARGIN", new_y="NEXT")


def _safe_text(text: str) -> str:
    """Sanitize text for PDF rendering - replace unsupported characters."""
    # Replace common unicode characters that Helvetica can't render
    replacements = {
        "\u2013": "-",   # en dash
        "\u2014": "--",  # em dash
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2026": "...", # ellipsis
        "\u00a0": " ",   # non-breaking space
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Encode to latin-1 and replace any remaining unsupported chars
    return text.encode("latin-1", errors="replace").decode("latin-1")
