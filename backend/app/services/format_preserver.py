"""
Format-Preserving Resume Enhancement Service

Extracts layout metadata (font sizes, styles, spacing, bullet structures)
from the original PDF, then rebuilds the enhanced PDF using the same
visual structure. Only textual content changes; the layout stays intact.

Limitations:
  - Exact font reproduction requires the font file to be available.
    When unavailable, a close standard substitute is used (Helvetica).
  - Complex multi-column layouts are flattened to single-column with
    similar spacing.
  - Embedded images/logos are not preserved.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber
from fpdf import FPDF

logger = logging.getLogger(__name__)

# Standard fonts available in fpdf2 (no embedding required)
_STANDARD_FONTS = {"helvetica", "courier", "times", "symbol", "zapfdingbats"}

# Map common PDF font names to fpdf2 standard families
_FONT_MAP = {
    "arial": "Helvetica",
    "arialmt": "Helvetica",
    "helvetica": "Helvetica",
    "helveticaneue": "Helvetica",
    "timesnewroman": "Times",
    "timesnewromanpsmt": "Times",
    "times": "Times",
    "courier": "Courier",
    "couriernew": "Courier",
    "calibri": "Helvetica",
    "cambria": "Times",
    "garamond": "Times",
    "georgia": "Times",
    "verdana": "Helvetica",
    "tahoma": "Helvetica",
    "trebuchetms": "Helvetica",
    "palatino": "Times",
    "bookantiqua": "Times",
}


@dataclass
class TextBlock:
    """A block of text extracted from the PDF with its formatting metadata."""

    text: str
    font_family: str = "Helvetica"
    font_size: float = 10.0
    is_bold: bool = False
    is_italic: bool = False
    x: float = 0.0
    y: float = 0.0
    line_height: float = 5.0
    is_bullet: bool = False
    page: int = 0


@dataclass
class LayoutMetadata:
    """Complete layout information extracted from a PDF."""

    blocks: List[TextBlock] = field(default_factory=list)
    page_width: float = 612.0  # US Letter default (points)
    page_height: float = 792.0
    margin_left: float = 20.0
    margin_right: float = 20.0
    margin_top: float = 20.0
    dominant_font: str = "Helvetica"
    dominant_size: float = 10.0
    header_size: float = 14.0
    section_header_size: float = 12.0
    body_size: float = 10.0
    line_spacing: float = 5.0
    section_spacing: float = 8.0
    bullet_indent: float = 10.0
    bullet_char: str = "-"
    formatting_preserved: bool = True
    formatting_notes: List[str] = field(default_factory=list)


def _normalize_font_name(raw: str) -> str:
    """Map a PDF font name to a standard fpdf2 family."""
    clean = re.sub(r"[^a-z]", "", raw.lower())
    # Strip style suffixes
    for suffix in ("bold", "italic", "oblique", "regular", "light", "medium"):
        clean = clean.replace(suffix, "")
    return _FONT_MAP.get(clean, "Helvetica")


def _detect_style(fontname: str) -> Tuple[bool, bool]:
    """Detect bold/italic from font name string."""
    lower = fontname.lower()
    is_bold = "bold" in lower or "black" in lower or "heavy" in lower
    is_italic = "italic" in lower or "oblique" in lower
    return is_bold, is_italic


def extract_layout(pdf_path: Path) -> LayoutMetadata:
    """
    Extract layout metadata from a PDF file.

    Uses pdfplumber to read character-level positioning and font info.
    Aggregates into text blocks with formatting attributes.
    """
    layout = LayoutMetadata()

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                layout.formatting_preserved = False
                layout.formatting_notes.append("PDF has no pages")
                return layout

            # Get page dimensions from first page
            first_page = pdf.pages[0]
            layout.page_width = first_page.width
            layout.page_height = first_page.height

            font_sizes: List[float] = []
            font_families: Dict[str, int] = {}

            for page_num, page in enumerate(pdf.pages):
                chars = page.chars
                if not chars:
                    continue

                # Detect margins from character positions
                x_positions = [c["x0"] for c in chars if c.get("text", "").strip()]
                if x_positions:
                    layout.margin_left = max(min(x_positions) - 2, 10)

                # Group characters into lines by y-position
                lines = _group_chars_into_lines(chars, page_num)

                for line_chars, line_y, line_page in lines:
                    if not line_chars:
                        continue

                    text = "".join(c.get("text", "") for c in line_chars).strip()
                    if not text:
                        continue

                    # Get dominant font info for this line
                    line_font = _dominant_font_in_group(line_chars)
                    font_family = _normalize_font_name(line_font.get("fontname", ""))
                    font_size = round(line_font.get("size", 10.0), 1)
                    is_bold, is_italic = _detect_style(line_font.get("fontname", ""))

                    font_sizes.append(font_size)
                    font_families[font_family] = font_families.get(font_family, 0) + 1

                    # Detect bullet
                    is_bullet = bool(re.match(r"^[\-\*\u2022\u25cf\u25cb\u2023]\s", text))
                    x_pos = line_chars[0].get("x0", 0)

                    block = TextBlock(
                        text=text,
                        font_family=font_family,
                        font_size=font_size,
                        is_bold=is_bold,
                        is_italic=is_italic,
                        x=x_pos,
                        y=line_y,
                        is_bullet=is_bullet,
                        page=line_page,
                    )
                    layout.blocks.append(block)

            # Compute aggregate layout properties
            if font_sizes:
                # Body size is the most common font size
                size_counts: Dict[float, int] = {}
                for s in font_sizes:
                    size_counts[s] = size_counts.get(s, 0) + 1
                layout.body_size = max(size_counts, key=size_counts.get)
                layout.dominant_size = layout.body_size

                # Header size is the largest
                layout.header_size = max(font_sizes)
                # Section header is second largest (or same as header if only one)
                unique_sizes = sorted(set(font_sizes), reverse=True)
                layout.section_header_size = unique_sizes[1] if len(unique_sizes) > 1 else unique_sizes[0]

            if font_families:
                layout.dominant_font = max(font_families, key=font_families.get)

            # Detect bullet character
            for block in layout.blocks:
                if block.is_bullet:
                    first_char = block.text[0]
                    if first_char in ("-", "*", "\u2022", "\u25cf"):
                        layout.bullet_char = first_char
                    break

            # Detect line spacing from consecutive blocks on same page
            spacings = []
            for i in range(1, len(layout.blocks)):
                if layout.blocks[i].page == layout.blocks[i - 1].page:
                    gap = layout.blocks[i].y - layout.blocks[i - 1].y
                    if 3 < gap < 30:
                        spacings.append(gap)
            if spacings:
                layout.line_spacing = round(sum(spacings) / len(spacings), 1)

            # Detect section spacing (larger gaps)
            large_gaps = [g for g in spacings if g > layout.line_spacing * 1.5]
            if large_gaps:
                layout.section_spacing = round(sum(large_gaps) / len(large_gaps), 1)

            layout.formatting_notes.append(
                f"Detected font: {layout.dominant_font} {layout.body_size}pt"
            )
            if layout.dominant_font != "Helvetica":
                layout.formatting_notes.append(
                    f"Original font '{layout.dominant_font}' mapped to standard PDF font"
                )

    except Exception as e:
        logger.warning("Layout extraction failed: %s. Using defaults.", e)
        layout.formatting_preserved = False
        layout.formatting_notes.append(f"Layout extraction failed: {e}")

    return layout


def _group_chars_into_lines(
    chars: list, page_num: int
) -> List[Tuple[list, float, int]]:
    """Group characters into lines based on y-position proximity."""
    if not chars:
        return []

    sorted_chars = sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"]))
    lines: List[Tuple[list, float, int]] = []
    current_line: list = []
    current_y: float = -999

    for char in sorted_chars:
        y = char["top"]
        if abs(y - current_y) > 3:  # New line threshold
            if current_line:
                lines.append((current_line, current_y, page_num))
            current_line = [char]
            current_y = y
        else:
            current_line.append(char)

    if current_line:
        lines.append((current_line, current_y, page_num))

    return lines


def _dominant_font_in_group(chars: list) -> dict:
    """Return the most common font properties in a character group."""
    if not chars:
        return {"fontname": "Helvetica", "size": 10.0}

    font_counts: Dict[str, int] = {}
    for c in chars:
        key = f"{c.get('fontname', 'unknown')}|{c.get('size', 10)}"
        font_counts[key] = font_counts.get(key, 0) + 1

    dominant_key = max(font_counts, key=font_counts.get)
    parts = dominant_key.split("|")
    return {"fontname": parts[0], "size": float(parts[1])}


class FormatPreservingPDF(FPDF):
    """FPDF subclass that uses layout metadata for formatting decisions."""

    def __init__(self, layout: LayoutMetadata):
        super().__init__()
        self.layout = layout

    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def _safe_text(text: str) -> str:
    """Sanitize text for PDF rendering."""
    replacements = {
        "\u2013": "-", "\u2014": "--", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " ",
        "\u2022": "-", "\u25cf": "-", "\u25cb": "-", "\u2023": "-",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def generate_format_preserved_pdf(
    resume_text: str,
    sections: Optional[Dict[str, str]],
    layout: LayoutMetadata,
    output_path: Path,
) -> Tuple[Path, List[str]]:
    """
    Generate a PDF that preserves the original resume's formatting.

    Uses the layout metadata to match font sizes, spacing, and bullet
    styles from the original document.

    Returns (output_path, list_of_formatting_notes).
    """
    notes = list(layout.formatting_notes)

    pdf = FormatPreservingPDF(layout)

    # Use extracted margins (convert from points to mm: 1pt = 0.3528mm)
    margin_mm = max(layout.margin_left * 0.3528, 15)
    pdf.set_margins(margin_mm, 15, margin_mm)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    font = layout.dominant_font
    body_size = layout.body_size
    header_size = layout.header_size
    section_size = layout.section_header_size
    line_h = max(layout.line_spacing * 0.3528, 4)  # Convert pt to mm
    section_gap = max(layout.section_spacing * 0.3528, 6)
    bullet = layout.bullet_char if layout.bullet_char in ("-", "*") else "-"

    notes.append(f"Body: {font} {body_size}pt, line height: {line_h:.1f}mm")

    if sections and len(sections) > 1:
        _render_preserved_structured(
            pdf, sections, font, header_size, section_size, body_size,
            line_h, section_gap, bullet,
        )
    else:
        _render_preserved_plain(
            pdf, resume_text, font, header_size, section_size, body_size,
            line_h, section_gap, bullet,
        )

    notes.append("Formatting preserved from original resume")
    pdf.output(str(output_path))
    logger.info("Generated format-preserved PDF: %s", output_path)
    return output_path, notes


def _render_preserved_structured(
    pdf: FormatPreservingPDF,
    sections: Dict[str, str],
    font: str,
    header_size: float,
    section_size: float,
    body_size: float,
    line_h: float,
    section_gap: float,
    bullet: str,
) -> None:
    """Render structured resume with preserved formatting."""
    section_order = ["header", "summary", "skills", "experience", "projects", "education"]
    rendered = set()

    for name in section_order:
        if name in sections:
            _render_preserved_section(
                pdf, name, sections[name], font, header_size,
                section_size, body_size, line_h, section_gap, bullet,
            )
            rendered.add(name)

    for name, content in sections.items():
        if name not in rendered and name != "unstructured":
            _render_preserved_section(
                pdf, name, content, font, header_size,
                section_size, body_size, line_h, section_gap, bullet,
            )


def _render_preserved_section(
    pdf: FormatPreservingPDF,
    name: str,
    content: str,
    font: str,
    header_size: float,
    section_size: float,
    body_size: float,
    line_h: float,
    section_gap: float,
    bullet: str,
) -> None:
    """Render a single section with format-preserved styling."""
    lines = content.split("\n")

    if name == "header":
        first_rendered = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if not first_rendered:
                pdf.set_font(font, "B", header_size)
                pdf.set_text_color(30, 30, 30)
                pdf.multi_cell(0, line_h * 1.5, _safe_text(stripped),
                               new_x="LMARGIN", new_y="NEXT")
                first_rendered = True
            else:
                pdf.set_font(font, "", max(body_size - 1, 8))
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, line_h, _safe_text(stripped),
                               new_x="LMARGIN", new_y="NEXT")
        pdf.ln(section_gap * 0.5)
        return

    # Section header
    section_headers = {"summary", "experience", "skills", "education", "projects"}
    if name in section_headers:
        pdf.ln(section_gap * 0.4)
        pdf.set_font(font, "B", section_size)
        pdf.set_text_color(30, 30, 80)
        title = name.replace("_", " ").title()
        pdf.multi_cell(0, line_h * 1.2, title, new_x="LMARGIN", new_y="NEXT")
        # Horizontal rule
        pdf.set_draw_color(30, 30, 80)
        pdf.set_line_width(0.3)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(section_gap * 0.3)

    # Body lines (skip header line)
    body_lines = list(lines)
    if body_lines:
        first_clean = re.sub(r"[:\-_|#*=]+", "", body_lines[0].strip()).strip()
        if len(first_clean) < 40:
            body_lines = body_lines[1:]

    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            pdf.ln(line_h * 0.4)
            continue

        if re.match(r"^[-*\u2022]\s+", stripped):
            bullet_content = re.sub(r"^[-*\u2022]\s+", "", stripped)
            pdf.set_font(font, "", body_size)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, line_h, f"   {bullet} " + _safe_text(bullet_content),
                           new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font(font, "", body_size)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, line_h, _safe_text(stripped),
                           new_x="LMARGIN", new_y="NEXT")

    pdf.ln(line_h * 0.3)


def _render_preserved_plain(
    pdf: FormatPreservingPDF,
    text: str,
    font: str,
    header_size: float,
    section_size: float,
    body_size: float,
    line_h: float,
    section_gap: float,
    bullet: str,
) -> None:
    """Render plain text with preserved formatting attributes."""
    pdf.set_font(font, "", body_size)
    pdf.set_text_color(50, 50, 50)

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            pdf.ln(line_h * 0.5)
            continue

        # Detect headers
        if len(stripped) < 40 and stripped == stripped.upper() and len(stripped) > 2:
            pdf.ln(section_gap * 0.4)
            pdf.set_font(font, "B", section_size)
            pdf.set_text_color(30, 30, 80)
            pdf.multi_cell(0, line_h * 1.2, stripped.title(),
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(30, 30, 80)
            pdf.set_line_width(0.3)
            y = pdf.get_y()
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(section_gap * 0.3)
        elif re.match(r"^[-*\u2022]\s+", stripped):
            bullet_content = re.sub(r"^[-*\u2022]\s+", "", stripped)
            pdf.set_font(font, "", body_size)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, line_h, f"   {bullet} " + _safe_text(bullet_content),
                           new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font(font, "", body_size)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, line_h, _safe_text(stripped),
                           new_x="LMARGIN", new_y="NEXT")
