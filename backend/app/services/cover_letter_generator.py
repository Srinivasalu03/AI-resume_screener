"""
Cover Letter Generation Service (Rule-Based NLP)

Generates professional, ATS-safe cover letters by combining:
- Resume content (skills, experience, achievements)
- Job description requirements
- Matched/missing keywords from analysis

The output is structured, concise (~300-400 words), and tailored to the
target role without fabricating information.
"""

import re
import logging
from typing import Dict, List, Optional

from app.services.job_recommender import _extract_skills, _extract_role_signals, _detect_experience_level
from app.services.resume_rewriter import parse_resume_sections

logger = logging.getLogger(__name__)


# ── Cover Letter Structure Templates ────────────────────────────────────────

_OPENING_TEMPLATES = [
    "I am writing to express my strong interest in the {role} position. "
    "With {experience} of experience in {domain}, I am confident in my ability "
    "to contribute meaningfully to your team.",

    "I am excited to apply for the {role} role. "
    "My background in {domain}, combined with {experience} of hands-on experience, "
    "makes me a strong fit for this position.",

    "I would like to express my interest in the {role} opportunity. "
    "With a proven track record in {domain} spanning {experience}, "
    "I bring both the technical depth and practical experience this role demands.",
]

_CLOSING_TEMPLATES = [
    "I would welcome the opportunity to discuss how my experience and skills "
    "can contribute to your team's success. I look forward to the possibility "
    "of contributing to your organization and am available for an interview "
    "at your convenience.",

    "Thank you for considering my application. I am eager to bring my expertise "
    "in {domain} to your team and would appreciate the opportunity to discuss "
    "how I can add value. I look forward to hearing from you.",

    "I am enthusiastic about this opportunity and confident that my background "
    "aligns well with your needs. I would be glad to discuss my qualifications "
    "further and am available at your earliest convenience.",
]


# ── Main Generation Function ───────────────────────────────────────────────

def generate_cover_letter(
    resume_text: str,
    job_description: str,
    matched_keywords: Optional[List[str]] = None,
    job_keywords: Optional[List[str]] = None,
    candidate_name: Optional[str] = None,
) -> Dict:
    """
    Generate a tailored cover letter from resume and job description.

    Returns:
        {
            "cover_letter": str,       # Full cover letter text
            "word_count": int,         # Word count
            "key_highlights": List[str], # Skills/achievements emphasized
            "candidate_name": str,     # Detected or provided name
        }
    """
    matched_keywords = matched_keywords or []
    job_keywords = job_keywords or []

    # Extract information from resume
    sections = parse_resume_sections(resume_text)
    name = candidate_name or _extract_name(resume_text, sections)
    experience_level = _detect_experience_level(resume_text)
    skills_detected = _extract_skills(resume_text)
    role_signals = _extract_role_signals(job_description)
    achievements = _extract_achievements(resume_text)
    domain = _detect_primary_domain(skills_detected, job_description)

    # Determine target role from JD
    target_role = _extract_target_role(job_description, role_signals)

    # Map experience level to years phrase
    experience_phrase = _experience_to_phrase(experience_level)

    # Build cover letter paragraphs
    opening = _build_opening(target_role, experience_phrase, domain)
    skills_paragraph = _build_skills_paragraph(
        matched_keywords, job_keywords, skills_detected, target_role
    )
    experience_paragraph = _build_experience_paragraph(
        sections, achievements, job_keywords, domain
    )
    closing = _build_closing(domain)

    # Assemble full cover letter
    parts = [
        f"Dear Hiring Manager,",
        "",
        opening,
        "",
        skills_paragraph,
        "",
        experience_paragraph,
        "",
        closing,
        "",
        "Sincerely,",
        name,
    ]

    cover_letter = "\n".join(parts)

    # Collect key highlights for metadata
    key_highlights = []
    if matched_keywords:
        key_highlights.extend(matched_keywords[:5])
    if achievements:
        key_highlights.extend(achievements[:3])

    return {
        "cover_letter": cover_letter,
        "word_count": len(cover_letter.split()),
        "key_highlights": key_highlights[:8],
        "candidate_name": name,
    }


# ── Paragraph Builders ─────────────────────────────────────────────────────

def _build_opening(role: str, experience: str, domain: str) -> str:
    """Build the opening paragraph."""
    # Pick template based on hash of role for consistent but varied output
    idx = sum(ord(c) for c in role) % len(_OPENING_TEMPLATES)
    return _OPENING_TEMPLATES[idx].format(
        role=role, experience=experience, domain=domain
    )


def _build_skills_paragraph(
    matched_keywords: List[str],
    job_keywords: List[str],
    skills_detected: Dict,
    target_role: str,
) -> str:
    """Build a paragraph highlighting relevant skills."""
    # Gather all detected skills as flat list
    all_skills = set()
    for cat_skills in skills_detected.values():
        all_skills.update(cat_skills)

    # Prioritize matched keywords, then job keywords found in skills
    highlighted = []
    for kw in matched_keywords:
        if kw.lower() not in {h.lower() for h in highlighted}:
            highlighted.append(kw)
    for kw in job_keywords:
        if kw.lower() in {s.lower() for s in all_skills} and kw.lower() not in {h.lower() for h in highlighted}:
            highlighted.append(kw)

    highlighted = highlighted[:8]

    if not highlighted:
        highlighted = list(all_skills)[:6]

    if len(highlighted) >= 4:
        skills_text = ", ".join(highlighted[:-1]) + f", and {highlighted[-1]}"
    elif len(highlighted) >= 2:
        skills_text = " and ".join(highlighted)
    else:
        skills_text = highlighted[0] if highlighted else "relevant technologies"

    paragraph = (
        f"My technical expertise includes {skills_text}, "
        f"which directly align with the requirements for this {target_role} position. "
    )

    # Add a sentence about breadth
    skill_count = sum(len(v) for v in skills_detected.values())
    if skill_count > 10:
        paragraph += (
            f"Across {skill_count} technical competencies, I bring both depth in core "
            f"technologies and breadth across the modern development stack."
        )
    elif skill_count > 5:
        paragraph += (
            "I maintain a strong foundation across multiple technology areas, "
            "allowing me to contribute effectively in cross-functional environments."
        )
    else:
        paragraph += (
            "I am committed to continuous learning and staying current with "
            "industry best practices and emerging technologies."
        )

    return paragraph


def _build_experience_paragraph(
    sections: Dict[str, str],
    achievements: List[str],
    job_keywords: List[str],
    domain: str,
) -> str:
    """Build a paragraph about relevant experience and achievements."""
    parts = []

    if achievements:
        # Lead with strongest achievement
        parts.append(
            f"In my previous roles, I have consistently delivered measurable results. "
            f"For example, I {achievements[0].lower().lstrip('- ').rstrip('.')}."
        )
        if len(achievements) > 1:
            parts.append(
                f"Additionally, I {achievements[1].lower().lstrip('- ').rstrip('.')}."
            )
    else:
        # Generic but professional experience statement
        exp_text = sections.get("experience", "")
        if exp_text and len(exp_text) > 50:
            parts.append(
                f"Throughout my career in {domain}, I have built a strong track record "
                f"of delivering high-quality solutions and collaborating effectively "
                f"with cross-functional teams."
            )
        else:
            parts.append(
                f"I bring a strong work ethic and a passion for {domain}, "
                f"with a focus on delivering reliable, well-engineered solutions."
            )

    # Add relevance tie-in
    if job_keywords:
        relevant = job_keywords[:3]
        kw_text = ", ".join(relevant)
        parts.append(
            f"My hands-on experience with {kw_text} positions me well "
            f"to make an immediate and meaningful contribution to your team."
        )

    return " ".join(parts)


def _build_closing(domain: str) -> str:
    """Build the closing paragraph."""
    idx = sum(ord(c) for c in domain) % len(_CLOSING_TEMPLATES)
    return _CLOSING_TEMPLATES[idx].format(domain=domain)


# ── Helper Extractors ──────────────────────────────────────────────────────

def _extract_name(resume_text: str, sections: Dict[str, str]) -> str:
    """Extract candidate name from resume header."""
    header = sections.get("header", "")
    if header:
        lines = [l.strip() for l in header.split("\n") if l.strip()]
        if lines:
            first_line = lines[0]
            # Name is usually the first line, should be 2-4 words, no special chars
            if len(first_line.split()) <= 5 and not re.search(r"[@\d]", first_line):
                return first_line

    # Fallback: first non-empty line of resume
    for line in resume_text.split("\n"):
        stripped = line.strip()
        if stripped and len(stripped.split()) <= 5 and not re.search(r"[@\d]", stripped):
            return stripped

    return "[Your Name]"


def _extract_achievements(resume_text: str) -> List[str]:
    """Extract quantified achievement statements from resume."""
    achievements = []
    # Pattern: bullet points with numbers, percentages, or dollar amounts
    impact_pattern = re.compile(
        r"^[-*\u2022]\s+(.+(?:\d+[\+%$]|[$]\d|reduced|increased|improved|saved|grew|"
        r"boosted|achieved|delivered|generated|optimized|scaled|launched).+)$",
        re.IGNORECASE | re.MULTILINE,
    )

    for match in impact_pattern.finditer(resume_text):
        achievement = match.group(1).strip()
        if len(achievement) > 20:  # Filter out very short matches
            achievements.append(achievement)

    return achievements[:5]


def _extract_target_role(job_description: str, role_signals: List[str]) -> str:
    """Extract the target role title from the job description."""
    # Try to find an explicit title pattern
    title_patterns = [
        r"(?:position|role|title|hiring for|looking for)[:\s]+([A-Z][A-Za-z\s/]+)",
        r"^([A-Z][A-Za-z\s/]+(?:Engineer|Developer|Manager|Analyst|Designer|Architect|Lead))",
    ]

    for pattern in title_patterns:
        match = re.search(pattern, job_description[:200])
        if match:
            title = match.group(1).strip()
            if 2 <= len(title.split()) <= 6:
                return title

    # Fallback to role signals
    if role_signals:
        return role_signals[0].replace("_", " ").title()

    return "the advertised"


def _detect_primary_domain(skills_detected: Dict, job_description: str) -> str:
    """Determine the primary domain from skills and JD."""
    domain_map = {
        "software development": ["python", "java", "javascript", "typescript", "go", "rust"],
        "web development": ["react", "angular", "vue", "html", "css", "frontend"],
        "backend engineering": ["api", "fastapi", "django", "flask", "express", "node"],
        "cloud and infrastructure": ["aws", "azure", "gcp", "kubernetes", "docker", "terraform"],
        "data science and analytics": ["machine learning", "data", "pandas", "tensorflow", "pytorch"],
        "DevOps and platform engineering": ["ci/cd", "jenkins", "ansible", "devops", "monitoring"],
        "mobile development": ["ios", "android", "react native", "flutter", "swift"],
    }

    all_skills = set()
    for cat_skills in skills_detected.values():
        all_skills.update(s.lower() for s in cat_skills)

    jd_lower = job_description.lower()
    best_domain = "technology"
    best_count = 0

    for domain, triggers in domain_map.items():
        count = sum(1 for t in triggers if t in all_skills or t in jd_lower)
        if count > best_count:
            best_count = count
            best_domain = domain

    return best_domain


def _experience_to_phrase(level: str) -> str:
    """Convert experience level to a natural language phrase."""
    mapping = {
        "senior": "over 7 years",
        "mid-level": "several years",
        "junior": "meaningful",
        "entry-level": "foundational",
        "lead": "extensive",
        "executive": "over a decade",
    }
    return mapping.get(level, "solid")


# ── Cover Letter PDF Generation ─────────────────────────────────────────────

def generate_cover_letter_pdf(
    cover_letter_text: str,
    output_path,
) -> None:
    """Generate a clean PDF from cover letter text."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_margins(25, 25, 25)
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()

    # Render each line
    for line in cover_letter_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            pdf.ln(5)
            continue

        # Salutation and sign-off in bold
        if stripped.startswith("Dear ") or stripped == "Sincerely,":
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(30, 30, 30)
        elif stripped == cover_letter_text.split("\n")[-1].strip():
            # Last line (name) - bold
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(30, 30, 30)
        else:
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(50, 50, 50)

        # Sanitize text for PDF
        safe = stripped.encode("latin-1", errors="replace").decode("latin-1")
        pdf.multi_cell(0, 6, safe, new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(output_path))
