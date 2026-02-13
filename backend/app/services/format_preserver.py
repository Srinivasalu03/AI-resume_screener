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
    semantic_role: str = "body"  # "section_heading", "sub_heading", "body", "bullet"


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
    sub_heading_size: float = 11.0  # For role/company/degree lines
    line_spacing: float = 5.0
    section_spacing: float = 8.0
    bullet_indent: float = 10.0
    bullet_char: str = "-"
    formatting_preserved: bool = True
    section_structure_preserved: bool = False
    formatting_notes: List[str] = field(default_factory=list)


# Section heading patterns for intelligent detection (no hardcoded names)
_SECTION_HEADING_PATTERNS = re.compile(
    r"^(summary|professional\s*summary|objective|profile|about\s*me|career\s*objective"
    r"|experience|work\s*experience|professional\s*experience|employment(?:\s*history)?"
    r"|skills|technical\s*skills|core\s*competencies|competencies|technologies|tech\s*stack"
    r"|education|academic|qualifications|certifications?(?:\s*(?:&|and)\s*education)?"
    r"|projects|key\s*projects|personal\s*projects"
    r"|additional\s*details|additional\s*information|extracurricular|activities"
    r"|awards|achievements|honors|publications|references|languages"
    r"|volunteer|interests|hobbies)$",
    re.IGNORECASE,
)

# Sub-heading signals: role titles, degrees, company names with dates
_DATE_PATTERN = re.compile(
    r"(20\d{2}|19\d{2}|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b"
    r"|present|current|\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

_ROLE_SIGNALS = re.compile(
    r"\b(engineer|developer|manager|analyst|designer|intern|lead|director"
    r"|coordinator|specialist|consultant|associate|architect|scientist"
    r"|administrator|officer|executive|president|vp|head\s+of"
    r"|bachelor|master|b\.?sc?|m\.?sc?|b\.?tech|m\.?tech|b\.?e|m\.?e"
    r"|ph\.?d|mba|diploma)\b",
    re.IGNORECASE,
)


def _classify_block_role(
    block: TextBlock,
    body_size: float,
    section_header_size: float,
) -> str:
    """
    Classify a text block's semantic role based on font size, style, and content.

    Returns one of: 'section_heading', 'sub_heading', 'body', 'bullet'
    """
    text = block.text.strip()
    if not text:
        return "body"

    # Bullets are always body-level
    if block.is_bullet:
        return "bullet"

    clean = re.sub(r"[:\-_|#*=]+", "", text).strip()

    # Section headings: short, bold/larger, match known patterns
    if len(clean) < 50 and _SECTION_HEADING_PATTERNS.match(clean):
        return "section_heading"

    # Also detect section headings by visual properties:
    # short + significantly larger than body + bold
    if (len(clean) < 50
            and block.font_size >= section_header_size - 0.5
            and block.is_bold
            and block.font_size > body_size + 0.5):
        return "section_heading"

    # Sub-headings: lines with dates, role signals, or bold + slightly larger
    has_date = bool(_DATE_PATTERN.search(text))
    has_role = bool(_ROLE_SIGNALS.search(text))

    if has_date and has_role:
        return "sub_heading"
    if has_date and block.is_bold:
        return "sub_heading"
    if has_role and block.is_bold and len(text) < 80:
        return "sub_heading"
    # Bold text that's slightly larger than body, not too long (role/company line)
    if (block.is_bold
            and block.font_size > body_size
            and len(text) < 80
            and not block.is_bullet):
        return "sub_heading"

    return "body"


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

            # Classify semantic roles for all blocks
            for block in layout.blocks:
                block.semantic_role = _classify_block_role(
                    block, layout.body_size, layout.section_header_size,
                )

            # Compute sub_heading_size from detected sub-headings
            sub_sizes = [b.font_size for b in layout.blocks if b.semantic_role == "sub_heading"]
            if sub_sizes:
                size_counts: Dict[float, int] = {}
                for s in sub_sizes:
                    size_counts[s] = size_counts.get(s, 0) + 1
                layout.sub_heading_size = max(size_counts, key=size_counts.get)
            else:
                # Default: midpoint between body and section header
                layout.sub_heading_size = round(
                    (layout.body_size + layout.section_header_size) / 2, 1
                )

            has_section_headings = any(
                b.semantic_role == "section_heading" for b in layout.blocks
            )
            has_sub_headings = any(
                b.semantic_role == "sub_heading" for b in layout.blocks
            )
            layout.section_structure_preserved = has_section_headings

            if has_section_headings:
                layout.formatting_notes.append(
                    f"Detected section structure with {sum(1 for b in layout.blocks if b.semantic_role == 'section_heading')} headings"
                )
            if has_sub_headings:
                layout.formatting_notes.append(
                    f"Detected {sum(1 for b in layout.blocks if b.semantic_role == 'sub_heading')} sub-headings (roles/degrees)"
                )

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


def _is_sub_heading_line(text: str) -> bool:
    """Check if a text line looks like a sub-heading (role/company/degree)."""
    if len(text) > 100 or not text.strip():
        return False
    has_date = bool(_DATE_PATTERN.search(text))
    has_role = bool(_ROLE_SIGNALS.search(text))
    if has_date and has_role:
        return True
    if has_date and len(text) < 80:
        return True
    if has_role and len(text) < 60:
        return True
    return False


def generate_format_preserved_pdf(
    resume_text: str,
    sections: Optional[Dict[str, str]],
    layout: LayoutMetadata,
    output_path: Path,
) -> Tuple[Path, List[str]]:
    """
    Generate a PDF that preserves the original resume's formatting
    with section-aware heading/body differentiation.

    Uses the layout metadata to match font sizes, spacing, and bullet
    styles from the original document. Enforces strict heading > sub-heading > body
    font size hierarchy.

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
    sub_heading_size = layout.sub_heading_size
    line_h = max(layout.line_spacing * 0.3528, 4)  # Convert pt to mm
    section_gap = max(layout.section_spacing * 0.3528, 6)
    bullet = layout.bullet_char if layout.bullet_char in ("-", "*") else "-"

    # Enforce font size hierarchy: section_header > sub_heading > body
    if sub_heading_size <= body_size:
        sub_heading_size = body_size + 1
    if section_size <= sub_heading_size:
        section_size = sub_heading_size + 1

    notes.append(
        f"Font hierarchy: section {section_size}pt > sub-heading {sub_heading_size}pt > body {body_size}pt"
    )

    sizing = _FontSizing(
        font=font,
        header_size=header_size,
        section_size=section_size,
        sub_heading_size=sub_heading_size,
        body_size=body_size,
        line_h=line_h,
        section_gap=section_gap,
        bullet=bullet,
    )

    if sections and len(sections) > 1:
        _render_preserved_structured(pdf, sections, sizing)
    else:
        _render_preserved_plain(pdf, resume_text, sizing)

    notes.append("Formatting and section structure preserved from original resume")
    pdf.output(str(output_path))
    logger.info("Generated section-aware format-preserved PDF: %s", output_path)
    return output_path, notes


@dataclass
class _FontSizing:
    """Bundle of font sizing parameters to reduce function argument count."""
    font: str
    header_size: float
    section_size: float
    sub_heading_size: float
    body_size: float
    line_h: float
    section_gap: float
    bullet: str


def _render_preserved_structured(
    pdf: FormatPreservingPDF,
    sections: Dict[str, str],
    sz: _FontSizing,
) -> None:
    """Render structured resume with section-aware formatting."""
    section_order = [
        "header", "summary", "skills", "experience", "projects", "education",
    ]
    rendered = set()

    for name in section_order:
        if name in sections:
            _render_preserved_section(pdf, name, sections[name], sz)
            rendered.add(name)

    # Remaining sections (e.g. "additional details") come after education
    for name, content in sections.items():
        if name not in rendered and name != "unstructured":
            # Insert extra spacing before additional sections
            pdf.ln(sz.section_gap * 0.6)
            _render_preserved_section(pdf, name, content, sz)


def _render_preserved_section(
    pdf: FormatPreservingPDF,
    name: str,
    content: str,
    sz: _FontSizing,
) -> None:
    """Render a single section with strict heading/body differentiation."""
    lines = content.split("\n")

    # ── Header (name + contact info) ──
    if name == "header":
        first_rendered = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if not first_rendered:
                pdf.set_font(sz.font, "B", sz.header_size)
                pdf.set_text_color(30, 30, 30)
                pdf.multi_cell(0, sz.line_h * 1.5, _safe_text(stripped),
                               new_x="LMARGIN", new_y="NEXT")
                first_rendered = True
            else:
                pdf.set_font(sz.font, "", max(sz.body_size - 1, 8))
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, sz.line_h, _safe_text(stripped),
                               new_x="LMARGIN", new_y="NEXT")
        pdf.ln(sz.section_gap * 0.5)
        return

    # ── Section heading ──
    # Retain original heading text from the first line
    known_sections = {
        "summary", "experience", "skills", "education", "projects",
        "additional_details", "additional details",
    }
    if name.lower().replace("_", " ") in {s.replace("_", " ") for s in known_sections} or name in known_sections:
        pdf.ln(sz.section_gap * 0.4)

        # Use original heading text (first line) instead of generating one
        original_heading = lines[0].strip() if lines else name.replace("_", " ").title()
        clean = re.sub(r"[:\-_|#*=]+", "", original_heading).strip()
        if clean and len(clean) < 50:
            heading_text = original_heading.strip().rstrip(":").rstrip("-").strip()
        else:
            heading_text = name.replace("_", " ").title()

        pdf.set_font(sz.font, "B", sz.section_size)
        pdf.set_text_color(30, 30, 80)
        pdf.multi_cell(0, sz.line_h * 1.2, _safe_text(heading_text),
                       new_x="LMARGIN", new_y="NEXT")
        # Horizontal rule
        pdf.set_draw_color(30, 30, 80)
        pdf.set_line_width(0.3)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(sz.section_gap * 0.3)

    # ── Body lines (skip header line) ──
    body_lines = list(lines)
    if body_lines:
        first_clean = re.sub(r"[:\-_|#*=]+", "", body_lines[0].strip()).strip()
        if len(first_clean) < 50:
            body_lines = body_lines[1:]

    # ── Section-specific rendering ──
    if name == "summary":
        _render_summary_body(pdf, body_lines, sz)
    elif name in ("experience", "projects", "education"):
        _render_hierarchical_body(pdf, body_lines, sz)
    else:
        _render_flat_body(pdf, body_lines, sz)

    pdf.ln(sz.line_h * 0.3)


def _render_summary_body(
    pdf: FormatPreservingPDF,
    lines: List[str],
    sz: _FontSizing,
) -> None:
    """Render summary as a single paragraph - no bullets, no line breaks."""
    # Combine all non-empty lines into one paragraph
    parts = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            # Remove bullet prefixes if accidentally present
            cleaned = re.sub(r"^[-*\u2022]\s+", "", stripped)
            parts.append(cleaned)
    paragraph = " ".join(parts)

    if paragraph:
        pdf.set_font(sz.font, "", sz.body_size)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, sz.line_h, _safe_text(paragraph),
                       new_x="LMARGIN", new_y="NEXT")


def _render_hierarchical_body(
    pdf: FormatPreservingPDF,
    lines: List[str],
    sz: _FontSizing,
) -> None:
    """
    Render Experience/Education/Projects with strict heading/body hierarchy.

    Sub-headings (role/company/degree lines) are rendered bold at sub_heading_size.
    Body content (bullets, descriptions) is rendered at body_size.
    """
    for line in lines:
        stripped = line.strip()
        if not stripped:
            pdf.ln(sz.line_h * 0.4)
            continue

        is_bullet = bool(re.match(r"^[-*\u2022]\s+", stripped))

        if is_bullet:
            bullet_content = re.sub(r"^[-*\u2022]\s+", "", stripped)
            pdf.set_font(sz.font, "", sz.body_size)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, sz.line_h,
                           f"   {sz.bullet} " + _safe_text(bullet_content),
                           new_x="LMARGIN", new_y="NEXT")
        elif _is_sub_heading_line(stripped):
            # Role / Company / Duration or Degree / Institution / Year
            pdf.ln(sz.line_h * 0.2)
            pdf.set_font(sz.font, "B", sz.sub_heading_size)
            pdf.set_text_color(40, 40, 60)
            pdf.multi_cell(0, sz.line_h * 1.1, _safe_text(stripped),
                           new_x="LMARGIN", new_y="NEXT")
        else:
            # Regular body text
            pdf.set_font(sz.font, "", sz.body_size)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, sz.line_h, _safe_text(stripped),
                           new_x="LMARGIN", new_y="NEXT")


def _render_flat_body(
    pdf: FormatPreservingPDF,
    lines: List[str],
    sz: _FontSizing,
) -> None:
    """Render body lines for sections without sub-heading hierarchy (skills, etc.)."""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            pdf.ln(sz.line_h * 0.4)
            continue

        if re.match(r"^[-*\u2022]\s+", stripped):
            bullet_content = re.sub(r"^[-*\u2022]\s+", "", stripped)
            pdf.set_font(sz.font, "", sz.body_size)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, sz.line_h,
                           f"   {sz.bullet} " + _safe_text(bullet_content),
                           new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font(sz.font, "", sz.body_size)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, sz.line_h, _safe_text(stripped),
                           new_x="LMARGIN", new_y="NEXT")


def _render_preserved_plain(
    pdf: FormatPreservingPDF,
    text: str,
    sz: _FontSizing,
) -> None:
    """Render plain text with section-aware formatting detection."""
    pdf.set_font(sz.font, "", sz.body_size)
    pdf.set_text_color(50, 50, 50)

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            pdf.ln(sz.line_h * 0.5)
            continue

        clean = re.sub(r"[:\-_|#*=]+", "", stripped).strip()

        # Detect section headings
        if len(clean) < 50 and _SECTION_HEADING_PATTERNS.match(clean):
            pdf.ln(sz.section_gap * 0.4)
            pdf.set_font(sz.font, "B", sz.section_size)
            pdf.set_text_color(30, 30, 80)
            pdf.multi_cell(0, sz.line_h * 1.2, _safe_text(stripped),
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(30, 30, 80)
            pdf.set_line_width(0.3)
            y = pdf.get_y()
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(sz.section_gap * 0.3)
        elif len(stripped) < 40 and stripped == stripped.upper() and len(stripped) > 2:
            # ALL CAPS short line → likely section heading
            pdf.ln(sz.section_gap * 0.4)
            pdf.set_font(sz.font, "B", sz.section_size)
            pdf.set_text_color(30, 30, 80)
            pdf.multi_cell(0, sz.line_h * 1.2, stripped.title(),
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(30, 30, 80)
            pdf.set_line_width(0.3)
            y = pdf.get_y()
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(sz.section_gap * 0.3)
        elif _is_sub_heading_line(stripped):
            pdf.ln(sz.line_h * 0.2)
            pdf.set_font(sz.font, "B", sz.sub_heading_size)
            pdf.set_text_color(40, 40, 60)
            pdf.multi_cell(0, sz.line_h * 1.1, _safe_text(stripped),
                           new_x="LMARGIN", new_y="NEXT")
        elif re.match(r"^[-*\u2022]\s+", stripped):
            bullet_content = re.sub(r"^[-*\u2022]\s+", "", stripped)
            pdf.set_font(sz.font, "", sz.body_size)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, sz.line_h,
                           f"   {sz.bullet} " + _safe_text(bullet_content),
                           new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font(sz.font, "", sz.body_size)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, sz.line_h, _safe_text(stripped),
                           new_x="LMARGIN", new_y="NEXT")
