"""
ATS Compatibility Checker Service

Evaluates resume text and PDF metadata for ATS (Applicant Tracking System)
compatibility. Checks include:
  - Section heading clarity
  - Standard section presence
  - Parsing reliability (special characters, encoding)
  - Content structure (bullets, length)
  - Contact information completeness
  - File structure issues

Each check produces a status (pass/warning/fail), explanation, and fix suggestion.
Final ATS score (0-100) is calculated from all check results.
"""

import re
import logging
from typing import Dict, List, Optional

from app.services.resume_rewriter import parse_resume_sections, SECTION_PATTERNS

logger = logging.getLogger(__name__)


# ── Check Result Statuses ──────────────────────────────────────────────────

STATUS_PASS = "pass"
STATUS_WARNING = "warning"
STATUS_FAIL = "fail"

# Points deducted per status
_DEDUCTIONS = {
    STATUS_PASS: 0,
    STATUS_WARNING: 5,
    STATUS_FAIL: 12,
}


# ── Standard Section Names ATS Systems Expect ─────────────────────────────

_REQUIRED_SECTIONS = {"experience", "skills", "education"}
_OPTIONAL_SECTIONS = {"summary", "projects"}

_STANDARD_HEADINGS = {
    "experience": ["Experience", "Work Experience", "Professional Experience", "Employment History"],
    "skills": ["Skills", "Technical Skills", "Core Competencies"],
    "education": ["Education", "Academic Background", "Qualifications"],
    "summary": ["Summary", "Professional Summary", "Objective", "Profile"],
    "projects": ["Projects", "Key Projects", "Personal Projects"],
}


# ── Main Check Function ───────────────────────────────────────────────────

def check_ats_compatibility(
    resume_text: str,
    filename: Optional[str] = None,
) -> Dict:
    """
    Run all ATS compatibility checks on resume text.

    Returns:
        {
            "score": float (0-100),
            "checks": List[Dict],  # Individual check results
            "summary": str,        # Overall assessment
            "pass_count": int,
            "warning_count": int,
            "fail_count": int,
        }
    """
    checks = []

    # Run all checks
    checks.append(_check_file_format(filename))
    checks.append(_check_section_headings(resume_text))
    checks.append(_check_required_sections(resume_text))
    checks.append(_check_contact_info(resume_text))
    checks.append(_check_parsing_characters(resume_text))
    checks.append(_check_bullet_structure(resume_text))
    checks.append(_check_resume_length(resume_text))
    checks.append(_check_date_formats(resume_text))
    checks.append(_check_tables_and_columns(resume_text))
    checks.append(_check_keyword_density(resume_text))

    # Calculate score
    total_deduction = sum(_DEDUCTIONS[c["status"]] for c in checks)
    score = max(0, 100 - total_deduction)

    pass_count = sum(1 for c in checks if c["status"] == STATUS_PASS)
    warning_count = sum(1 for c in checks if c["status"] == STATUS_WARNING)
    fail_count = sum(1 for c in checks if c["status"] == STATUS_FAIL)

    summary = _generate_summary(score, pass_count, warning_count, fail_count)

    return {
        "score": round(score, 1),
        "checks": checks,
        "summary": summary,
        "pass_count": pass_count,
        "warning_count": warning_count,
        "fail_count": fail_count,
    }


# ── Individual Check Functions ─────────────────────────────────────────────

def _check_file_format(filename: Optional[str]) -> Dict:
    """Check if the file format is ATS-friendly."""
    if not filename:
        return {
            "name": "File Format",
            "category": "file",
            "status": STATUS_PASS,
            "message": "PDF format detected - widely accepted by ATS systems.",
            "fix": None,
        }

    ext = filename.lower().split(".")[-1] if "." in filename else ""

    if ext == "pdf":
        return {
            "name": "File Format",
            "category": "file",
            "status": STATUS_PASS,
            "message": "PDF format is accepted by most ATS systems.",
            "fix": None,
        }
    elif ext in ("doc", "docx"):
        return {
            "name": "File Format",
            "category": "file",
            "status": STATUS_PASS,
            "message": "Word document format is well-supported by ATS systems.",
            "fix": None,
        }
    else:
        return {
            "name": "File Format",
            "category": "file",
            "status": STATUS_FAIL,
            "message": f"File format '.{ext}' may not be parseable by ATS systems.",
            "fix": "Convert your resume to PDF or DOCX format for best compatibility.",
        }


def _check_section_headings(resume_text: str) -> Dict:
    """Check if section headings are clear and standard."""
    sections = parse_resume_sections(resume_text)

    if "unstructured" in sections:
        return {
            "name": "Section Headings",
            "category": "structure",
            "status": STATUS_FAIL,
            "message": "No clear section headings detected. ATS systems rely on standard headings to parse resume content.",
            "fix": "Add clear section headings like 'Experience', 'Skills', 'Education' on their own lines.",
        }

    detected_sections = [k for k in sections.keys() if k != "header"]

    if len(detected_sections) >= 3:
        return {
            "name": "Section Headings",
            "category": "structure",
            "status": STATUS_PASS,
            "message": f"Clear section headings detected: {', '.join(s.title() for s in detected_sections)}.",
            "fix": None,
        }
    elif len(detected_sections) >= 1:
        return {
            "name": "Section Headings",
            "category": "structure",
            "status": STATUS_WARNING,
            "message": f"Only {len(detected_sections)} section heading(s) detected. ATS works best with clearly defined sections.",
            "fix": "Ensure you have separate headings for Experience, Skills, and Education.",
        }
    else:
        return {
            "name": "Section Headings",
            "category": "structure",
            "status": STATUS_FAIL,
            "message": "No standard section headings found.",
            "fix": "Use standard headings: 'Experience', 'Skills', 'Education', 'Summary'.",
        }


def _check_required_sections(resume_text: str) -> Dict:
    """Check for presence of required resume sections."""
    sections = parse_resume_sections(resume_text)
    found = set(sections.keys()) - {"header", "unstructured"}

    missing = _REQUIRED_SECTIONS - found
    has_optional = _OPTIONAL_SECTIONS & found

    if not missing:
        msg = "All required sections present (Experience, Skills, Education)."
        if has_optional:
            msg += f" Optional sections also found: {', '.join(s.title() for s in has_optional)}."
        return {
            "name": "Required Sections",
            "category": "content",
            "status": STATUS_PASS,
            "message": msg,
            "fix": None,
        }
    elif len(missing) == 1:
        return {
            "name": "Required Sections",
            "category": "content",
            "status": STATUS_WARNING,
            "message": f"Missing section: {', '.join(s.title() for s in missing)}. Most ATS systems expect this section.",
            "fix": f"Add a '{missing.pop().title()}' section to your resume.",
        }
    else:
        return {
            "name": "Required Sections",
            "category": "content",
            "status": STATUS_FAIL,
            "message": f"Missing sections: {', '.join(s.title() for s in missing)}. ATS may not parse your resume correctly.",
            "fix": "Add the missing sections with clear headings.",
        }


def _check_contact_info(resume_text: str) -> Dict:
    """Check for presence of email and phone in resume."""
    has_email = bool(re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", resume_text))
    has_phone = bool(re.search(r"[\+]?[\d\s\-().]{7,15}", resume_text[:500]))  # Check top of resume

    if has_email and has_phone:
        return {
            "name": "Contact Information",
            "category": "content",
            "status": STATUS_PASS,
            "message": "Email and phone number detected in resume.",
            "fix": None,
        }
    elif has_email:
        return {
            "name": "Contact Information",
            "category": "content",
            "status": STATUS_WARNING,
            "message": "Email found but phone number may be missing. Some ATS systems require both.",
            "fix": "Add a phone number to your contact information section.",
        }
    elif has_phone:
        return {
            "name": "Contact Information",
            "category": "content",
            "status": STATUS_WARNING,
            "message": "Phone found but email may be missing.",
            "fix": "Add a professional email address to your contact section.",
        }
    else:
        return {
            "name": "Contact Information",
            "category": "content",
            "status": STATUS_FAIL,
            "message": "No email or phone number detected. ATS systems need contact details to create candidate records.",
            "fix": "Add your email and phone number at the top of your resume.",
        }


def _check_parsing_characters(resume_text: str) -> Dict:
    """Check for characters that may cause ATS parsing issues."""
    issues = []

    # Check for excessive special characters
    special_chars = re.findall(r"[^\w\s.,;:!?@#$%&*()\-+=/\\\"\'`~\[\]{}|<>]", resume_text)
    if len(special_chars) > 10:
        issues.append(f"Found {len(special_chars)} unusual characters that may confuse ATS parsers")

    # Check for unicode that might not render
    non_ascii = re.findall(r"[^\x00-\x7F]", resume_text)
    # Filter out common acceptable unicode (em dash, quotes, bullets)
    problematic = [c for c in non_ascii if c not in "\u2013\u2014\u2018\u2019\u201c\u201d\u2022\u2026\u00b7"]
    if len(problematic) > 5:
        issues.append("Contains non-standard characters that some ATS systems cannot process")

    # Check for all-caps sections (harder to parse)
    all_caps_lines = [l for l in resume_text.split("\n") if l.strip() and l.strip() == l.strip().upper() and len(l.strip()) > 20]
    if len(all_caps_lines) > 3:
        issues.append("Multiple all-caps lines detected - some ATS systems struggle with all-caps text")

    if not issues:
        return {
            "name": "Character Compatibility",
            "category": "parsing",
            "status": STATUS_PASS,
            "message": "Text uses ATS-compatible characters and encoding.",
            "fix": None,
        }
    elif len(issues) == 1:
        return {
            "name": "Character Compatibility",
            "category": "parsing",
            "status": STATUS_WARNING,
            "message": issues[0] + ".",
            "fix": "Replace special characters with standard ASCII equivalents.",
        }
    else:
        return {
            "name": "Character Compatibility",
            "category": "parsing",
            "status": STATUS_FAIL,
            "message": "; ".join(issues) + ".",
            "fix": "Clean up special characters, avoid all-caps blocks, use standard text formatting.",
        }


def _check_bullet_structure(resume_text: str) -> Dict:
    """Check if experience uses proper bullet points."""
    bullets = re.findall(r"^[\s]*[-*\u2022]\s+", resume_text, re.MULTILINE)
    lines = [l.strip() for l in resume_text.split("\n") if l.strip()]
    total_lines = len(lines)

    if len(bullets) >= 5:
        return {
            "name": "Bullet Point Structure",
            "category": "formatting",
            "status": STATUS_PASS,
            "message": f"Good use of bullet points ({len(bullets)} found). ATS systems parse bulleted content reliably.",
            "fix": None,
        }
    elif len(bullets) >= 2:
        return {
            "name": "Bullet Point Structure",
            "category": "formatting",
            "status": STATUS_WARNING,
            "message": f"Only {len(bullets)} bullet points found. Experience sections should use bullet points for each achievement.",
            "fix": "Add bullet points (use - or *) for each experience item and achievement.",
        }
    else:
        return {
            "name": "Bullet Point Structure",
            "category": "formatting",
            "status": STATUS_WARNING,
            "message": "Few or no bullet points detected. Dense paragraph text is harder for ATS to parse.",
            "fix": "Break experience into bullet points starting with action verbs.",
        }


def _check_resume_length(resume_text: str) -> Dict:
    """Check if resume length is appropriate."""
    word_count = len(resume_text.split())

    if 200 <= word_count <= 1000:
        return {
            "name": "Resume Length",
            "category": "content",
            "status": STATUS_PASS,
            "message": f"Resume length ({word_count} words) is appropriate for ATS processing.",
            "fix": None,
        }
    elif word_count < 200:
        return {
            "name": "Resume Length",
            "category": "content",
            "status": STATUS_WARNING,
            "message": f"Resume is quite short ({word_count} words). Short resumes may lack enough keywords for ATS matching.",
            "fix": "Consider expanding your experience bullets with more detail and relevant keywords.",
        }
    elif word_count <= 1500:
        return {
            "name": "Resume Length",
            "category": "content",
            "status": STATUS_PASS,
            "message": f"Resume length ({word_count} words) is within acceptable range.",
            "fix": None,
        }
    else:
        return {
            "name": "Resume Length",
            "category": "content",
            "status": STATUS_WARNING,
            "message": f"Resume is quite long ({word_count} words). Some ATS systems truncate after 2 pages.",
            "fix": "Consider trimming to focus on the most relevant experience and skills.",
        }


def _check_date_formats(resume_text: str) -> Dict:
    """Check if dates are in a consistent, ATS-parseable format."""
    # Common date patterns ATS can parse
    standard_dates = re.findall(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{4}\b",
        resume_text
    )

    year_ranges = re.findall(r"\b\d{4}\s*[-\u2013]\s*(?:\d{4}|[Pp]resent|[Cc]urrent)\b", resume_text)
    mm_yyyy = re.findall(r"\b\d{1,2}/\d{4}\b", resume_text)

    total_dates = len(standard_dates) + len(year_ranges) + len(mm_yyyy)

    if total_dates >= 2:
        return {
            "name": "Date Formats",
            "category": "parsing",
            "status": STATUS_PASS,
            "message": f"Dates are in ATS-readable format ({total_dates} date references found).",
            "fix": None,
        }
    elif total_dates == 1:
        return {
            "name": "Date Formats",
            "category": "parsing",
            "status": STATUS_WARNING,
            "message": "Only one date reference found. ATS systems use dates to calculate experience duration.",
            "fix": "Add dates to each role in format: 'Month Year - Month Year' (e.g., 'Jan 2020 - Present').",
        }
    else:
        return {
            "name": "Date Formats",
            "category": "parsing",
            "status": STATUS_WARNING,
            "message": "No standard date formats detected. ATS uses dates to compute tenure and experience.",
            "fix": "Add employment dates in a consistent format like 'Jan 2020 - Dec 2023'.",
        }


def _check_tables_and_columns(resume_text: str) -> Dict:
    """Check for indicators of tables or multi-column layouts."""
    issues = []

    # Detect tab-heavy formatting (suggests columns/tables)
    tab_count = resume_text.count("\t")
    if tab_count > 10:
        issues.append("Heavy tab usage suggests a multi-column or table layout")

    # Detect pipe characters (table separators)
    pipe_lines = [l for l in resume_text.split("\n") if l.count("|") >= 2]
    if len(pipe_lines) > 2:
        issues.append("Pipe characters suggest table formatting")

    # Detect very short adjacent lines (may indicate columns)
    lines = resume_text.split("\n")
    short_adjacent = 0
    for i in range(len(lines) - 1):
        if 3 < len(lines[i].strip()) < 25 and 3 < len(lines[i+1].strip()) < 25:
            short_adjacent += 1
    if short_adjacent > 8:
        issues.append("Many short adjacent lines may indicate multi-column layout")

    if not issues:
        return {
            "name": "Layout Compatibility",
            "category": "formatting",
            "status": STATUS_PASS,
            "message": "No table or multi-column layout issues detected. Single-column layouts parse best.",
            "fix": None,
        }
    else:
        return {
            "name": "Layout Compatibility",
            "category": "formatting",
            "status": STATUS_WARNING,
            "message": "; ".join(issues) + ". Multi-column layouts and tables often cause ATS parsing failures.",
            "fix": "Use a single-column layout without tables. Present skills as comma-separated lists instead.",
        }


def _check_keyword_density(resume_text: str) -> Dict:
    """Check if resume has sufficient keyword-rich content."""
    words = resume_text.lower().split()
    word_count = len(words)

    if word_count == 0:
        return {
            "name": "Keyword Density",
            "category": "content",
            "status": STATUS_FAIL,
            "message": "No text content found.",
            "fix": "Ensure your resume contains readable text content.",
        }

    # Check for unique words (indicates content richness)
    unique_words = set(words)
    unique_ratio = len(unique_words) / word_count

    # Check for action verbs
    action_verbs = {"developed", "implemented", "designed", "managed", "led", "built",
                    "created", "delivered", "improved", "reduced", "increased", "launched",
                    "automated", "optimized", "deployed", "configured", "analyzed", "established"}
    verb_count = sum(1 for w in words if w in action_verbs)

    if verb_count >= 5 and unique_ratio > 0.3:
        return {
            "name": "Keyword Density",
            "category": "content",
            "status": STATUS_PASS,
            "message": f"Good keyword variety with {verb_count} action verbs. ATS keyword matching will work effectively.",
            "fix": None,
        }
    elif verb_count >= 2:
        return {
            "name": "Keyword Density",
            "category": "content",
            "status": STATUS_WARNING,
            "message": f"Only {verb_count} action verbs detected. More action verbs improve ATS keyword matching.",
            "fix": "Start experience bullets with strong action verbs: Built, Developed, Implemented, Led, etc.",
        }
    else:
        return {
            "name": "Keyword Density",
            "category": "content",
            "status": STATUS_WARNING,
            "message": "Low action verb count. ATS systems match against job description keywords.",
            "fix": "Use industry-standard action verbs and include relevant technical keywords.",
        }


# ── Summary Generation ────────────────────────────────────────────────────

def _generate_summary(score: float, passes: int, warnings: int, fails: int) -> str:
    """Generate an overall ATS compatibility summary."""
    if score >= 85:
        return (
            f"Your resume scores {score:.0f}/100 for ATS compatibility. "
            f"It is well-structured and should parse correctly through most ATS systems. "
            f"All {passes} core checks passed."
        )
    elif score >= 65:
        return (
            f"Your resume scores {score:.0f}/100 for ATS compatibility. "
            f"It has a good structure with {warnings} area(s) that could be improved. "
            f"Addressing the warnings below will improve parsing reliability."
        )
    elif score >= 40:
        return (
            f"Your resume scores {score:.0f}/100 for ATS compatibility. "
            f"There are {warnings} warning(s) and {fails} issue(s) that may prevent "
            f"ATS systems from correctly parsing your resume. Review the fixes below."
        )
    else:
        return (
            f"Your resume scores {score:.0f}/100 for ATS compatibility. "
            f"Significant formatting issues detected ({fails} failures). "
            f"Your resume may be rejected by ATS systems before reaching a recruiter. "
            f"Fixing the issues below is strongly recommended."
        )
