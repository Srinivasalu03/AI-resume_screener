"""
Resume Section Scoring Service

Scores individual resume sections (Skills, Experience, Projects, Education)
independently against a job description. Each section receives a confidence
score (0-100), an explanation of why, and lists of matched/missing elements.

Scoring approach per section:
  - Skills: keyword overlap (50%) + tool relevance (30%) + depth indicators (20%)
  - Experience: role relevance (40%) + impact statements (40%) + keyword presence (20%)
  - Projects: tech stack match (50%) + complexity indicators (30%) + outcomes (20%)
  - Education: degree relevance (60%) + level alignment (40%), with a fair baseline
"""

import re
import logging
from typing import Dict, List, Optional

from app.services.resume_rewriter import parse_resume_sections, ACTION_VERBS
from app.services.nlp_matcher import extract_keywords, preprocess_text
from app.services.job_recommender import _extract_skills, _extract_role_signals

logger = logging.getLogger(__name__)


# ── Depth / Proficiency Indicators ──────────────────────────────────────────

_PROFICIENCY_WORDS = re.compile(
    r"\b(expert|advanced|proficient|intermediate|experienced|certified|"
    r"specialist|mastery|fluent|competent)\b",
    re.IGNORECASE,
)

_IMPACT_PATTERN = re.compile(
    r"(\d+[\+%$]|[$]\d|reduced|increased|improved|saved|grew|boosted|"
    r"achieved|delivered|generated|optimized)",
    re.IGNORECASE,
)

_COMPLEXITY_WORDS = re.compile(
    r"\b(scalable|distributed|microservices|production|enterprise|high[- ]?availability|"
    r"real[- ]?time|large[- ]?scale|million|thousand|concurrent|multi[- ]?tenant|"
    r"deployed|launched|open[- ]?source|api|full[- ]?stack)\b",
    re.IGNORECASE,
)

_OUTCOME_WORDS = re.compile(
    r"\b(result|outcome|impact|improvement|growth|revenue|users|traffic|"
    r"performance|uptime|latency|accuracy|efficiency|award|recognition|"
    r"published|github|deployed|live|production)\b",
    re.IGNORECASE,
)

_DEGREE_FIELDS = {
    "computer science": 1.0,
    "software engineering": 1.0,
    "computer engineering": 1.0,
    "information technology": 0.9,
    "data science": 0.9,
    "artificial intelligence": 0.9,
    "machine learning": 0.9,
    "electrical engineering": 0.8,
    "mathematics": 0.8,
    "statistics": 0.8,
    "information systems": 0.8,
    "cybersecurity": 0.85,
    "physics": 0.7,
    "engineering": 0.75,
    "business": 0.5,
    "management": 0.5,
    "economics": 0.5,
}

_DEGREE_LEVELS = {
    "phd": 1.0,
    "ph.d": 1.0,
    "doctorate": 1.0,
    "master": 0.9,
    "m.s.": 0.9,
    "m.sc": 0.9,
    "mba": 0.8,
    "bachelor": 0.75,
    "b.s.": 0.75,
    "b.sc": 0.75,
    "b.tech": 0.75,
    "b.e.": 0.75,
    "associate": 0.5,
    "diploma": 0.45,
    "bootcamp": 0.4,
    "certificate": 0.4,
    "certification": 0.4,
}


# ── Section Scoring Functions ───────────────────────────────────────────────

def _score_skills(
    skills_text: str,
    job_keywords: List[str],
    job_description: str,
) -> Dict:
    """Score skills section: keyword overlap (50%) + tool relevance (30%) + depth (20%)."""
    if not skills_text or len(skills_text.strip()) < 5:
        return {
            "score": None,
            "explanation": "Skills section not found in resume.",
            "matched_elements": [],
            "missing_elements": job_keywords[:5] if job_keywords else [],
            "weak_areas": ["No skills section detected"],
        }

    skills_lower = skills_text.lower()

    # Signal 1: Keyword overlap (50%)
    matched_kws = []
    missing_kws = []
    for kw in job_keywords:
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", skills_lower):
            matched_kws.append(kw)
        else:
            missing_kws.append(kw)

    keyword_ratio = len(matched_kws) / max(len(job_keywords), 1)

    # Signal 2: Tool/framework relevance (30%)
    detected = _extract_skills(skills_text)
    total_tools = sum(len(v) for v in detected.values())
    tool_score = min(total_tools / 8, 1.0)  # 8+ recognized tools = full marks

    # Signal 3: Depth indicators (20%)
    proficiency_hits = len(_PROFICIENCY_WORDS.findall(skills_text))
    depth_score = min(proficiency_hits / 3, 1.0)  # 3+ depth indicators = full marks

    raw = (0.50 * keyword_ratio + 0.30 * tool_score + 0.20 * depth_score) * 100
    score = round(min(raw, 100.0), 1)

    # Build explanation
    explanation = _build_skills_explanation(score, matched_kws, missing_kws, total_tools)

    weak = []
    if depth_score < 0.5:
        weak.append("Consider adding proficiency levels (e.g., 'Advanced Python')")
    if total_tools < 4:
        weak.append("List more specific tools and frameworks")

    return {
        "score": score,
        "explanation": explanation,
        "matched_elements": matched_kws[:8],
        "missing_elements": missing_kws[:5],
        "weak_areas": weak,
    }


def _score_experience(
    experience_text: str,
    job_keywords: List[str],
    job_description: str,
) -> Dict:
    """Score experience: role relevance (40%) + impact (40%) + keywords (20%)."""
    if not experience_text or len(experience_text.strip()) < 10:
        return {
            "score": None,
            "explanation": "Experience section not found in resume.",
            "matched_elements": [],
            "missing_elements": [],
            "weak_areas": ["No experience section detected"],
        }

    exp_lower = experience_text.lower()

    # Signal 1: Role relevance (40%)
    resume_roles = _extract_role_signals(experience_text)
    jd_roles = _extract_role_signals(job_description)
    if jd_roles and resume_roles:
        role_overlap = len(set(resume_roles) & set(jd_roles))
        role_score = min(role_overlap / max(len(jd_roles), 1), 1.0)
    elif resume_roles:
        role_score = 0.5  # Has roles but can't compare
    else:
        role_score = 0.3  # No clear roles detected

    # Signal 2: Impact statements (40%)
    bullets = [l.strip() for l in experience_text.split("\n") if l.strip().startswith(("-", "•", "*"))]
    total_bullets = max(len(bullets), 1)

    impact_count = sum(1 for b in bullets if _IMPACT_PATTERN.search(b))
    action_count = sum(
        1 for b in bullets
        if any(b.lstrip("-•* ").startswith(v) for v in ACTION_VERBS)
    )

    impact_ratio = impact_count / total_bullets
    action_ratio = action_count / total_bullets
    impact_score = min((impact_ratio * 0.6 + action_ratio * 0.4), 1.0)

    # Signal 3: Keyword presence (20%)
    matched_kws = [
        kw for kw in job_keywords
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", exp_lower)
    ]
    kw_ratio = len(matched_kws) / max(len(job_keywords), 1)

    raw = (0.40 * role_score + 0.40 * impact_score + 0.20 * kw_ratio) * 100
    score = round(min(raw, 100.0), 1)

    explanation = _build_experience_explanation(
        score, resume_roles, impact_count, total_bullets, action_count
    )

    matched_el = []
    if resume_roles:
        matched_el.append(f"Role signals: {', '.join(resume_roles[:3])}")
    if impact_count:
        matched_el.append(f"{impact_count} quantified impact statement(s)")
    if action_count:
        matched_el.append(f"{action_count} strong action verb(s)")
    matched_el.extend(matched_kws[:4])

    weak = []
    if impact_ratio < 0.3:
        weak.append("Add quantified results (numbers, percentages, metrics)")
    if action_ratio < 0.5:
        weak.append("Start more bullets with strong action verbs")
    if kw_ratio < 0.3:
        weak.append("Incorporate more job description keywords into experience bullets")

    missing_kws = [kw for kw in job_keywords if kw not in matched_kws]

    return {
        "score": score,
        "explanation": explanation,
        "matched_elements": matched_el,
        "missing_elements": missing_kws[:5],
        "weak_areas": weak,
    }


def _score_projects(
    projects_text: str,
    job_keywords: List[str],
    job_description: str,
) -> Dict:
    """Score projects: tech stack (50%) + complexity (30%) + outcomes (20%)."""
    if not projects_text or len(projects_text.strip()) < 10:
        return {
            "score": None,
            "explanation": "Projects section not found in resume.",
            "matched_elements": [],
            "missing_elements": [],
            "weak_areas": ["Adding a projects section can strengthen your resume"],
        }

    proj_lower = projects_text.lower()

    # Signal 1: Tech stack match (50%)
    detected = _extract_skills(projects_text)
    all_proj_skills = set()
    for cat_skills in detected.values():
        all_proj_skills.update(cat_skills)

    matched_tech = [
        kw for kw in job_keywords
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", proj_lower)
    ]
    tech_ratio = len(matched_tech) / max(len(job_keywords), 1)
    # Also reward having many recognized technologies
    tech_breadth = min(len(all_proj_skills) / 5, 1.0)
    tech_score = 0.7 * tech_ratio + 0.3 * tech_breadth

    # Signal 2: Complexity indicators (30%)
    complexity_hits = len(_COMPLEXITY_WORDS.findall(projects_text))
    complexity_score = min(complexity_hits / 4, 1.0)

    # Signal 3: Outcomes (20%)
    outcome_hits = len(_OUTCOME_WORDS.findall(projects_text))
    outcome_score = min(outcome_hits / 3, 1.0)

    raw = (0.50 * tech_score + 0.30 * complexity_score + 0.20 * outcome_score) * 100
    score = round(min(raw, 100.0), 1)

    explanation = _build_projects_explanation(
        score, matched_tech, all_proj_skills, complexity_hits, outcome_hits
    )

    matched_el = []
    if matched_tech:
        matched_el.append(f"Matching tech: {', '.join(matched_tech[:5])}")
    if complexity_hits:
        matched_el.append(f"{complexity_hits} complexity indicator(s)")
    if outcome_hits:
        matched_el.append(f"{outcome_hits} outcome mention(s)")

    weak = []
    if complexity_hits < 2:
        weak.append("Describe project scale and technical complexity")
    if outcome_hits < 2:
        weak.append("Add measurable outcomes or deployment details")
    if not matched_tech:
        weak.append("Use technologies mentioned in the job description")

    missing_tech = [kw for kw in job_keywords if kw not in matched_tech]

    return {
        "score": score,
        "explanation": explanation,
        "matched_elements": matched_el,
        "missing_elements": missing_tech[:5],
        "weak_areas": weak,
    }


def _score_education(
    education_text: str,
    job_keywords: List[str],
    job_description: str,
) -> Dict:
    """Score education: degree relevance (60%) + level alignment (40%). Fair baseline of 50."""
    if not education_text or len(education_text.strip()) < 5:
        return {
            "score": None,
            "explanation": "Education section not found in resume.",
            "matched_elements": [],
            "missing_elements": [],
            "weak_areas": ["Consider adding education or relevant certifications"],
        }

    edu_lower = education_text.lower()

    # Signal 1: Degree field relevance (60%)
    best_field_score = 0.0
    matched_field = None
    for field, relevance in _DEGREE_FIELDS.items():
        if field in edu_lower:
            if relevance > best_field_score:
                best_field_score = relevance
                matched_field = field

    # If no recognized field, give a fair baseline
    if best_field_score == 0:
        best_field_score = 0.4  # Fair baseline for unrecognized fields
        matched_field = "general degree"

    # Signal 2: Degree level (40%)
    best_level_score = 0.0
    matched_level = None
    for level, weight in _DEGREE_LEVELS.items():
        if level in edu_lower:
            if weight > best_level_score:
                best_level_score = weight
                matched_level = level

    if best_level_score == 0:
        best_level_score = 0.4  # Fair baseline
        matched_level = "degree detected"

    raw = (0.60 * best_field_score + 0.40 * best_level_score) * 100
    # Apply fair baseline: minimum 30 for any education content
    score = round(max(min(raw, 100.0), 30.0), 1)

    explanation = _build_education_explanation(score, matched_field, matched_level)

    matched_el = []
    if matched_field and matched_field != "general degree":
        matched_el.append(f"Relevant field: {matched_field.title()}")
    if matched_level and matched_level != "degree detected":
        matched_el.append(f"Degree level: {matched_level.title()}")

    # Check for certifications
    cert_pattern = re.compile(r"\b(certified|certification|certificate|aws|azure|gcp|pmp|scrum)\b", re.IGNORECASE)
    certs = cert_pattern.findall(education_text)
    if certs:
        matched_el.append(f"Certifications: {', '.join(set(c.upper() for c in certs[:3]))}")

    weak = []
    if best_field_score < 0.6:
        weak.append("Degree field has limited direct relevance to the role")
    if not certs:
        weak.append("Consider adding relevant certifications")

    return {
        "score": score,
        "explanation": explanation,
        "matched_elements": matched_el,
        "missing_elements": [],
        "weak_areas": weak,
    }


# ── Explanation Builders ────────────────────────────────────────────────────

def _build_skills_explanation(
    score: float, matched: List[str], missing: List[str], tool_count: int
) -> str:
    if score >= 80:
        base = "Excellent skills alignment. Your skills section covers most job requirements."
    elif score >= 60:
        base = "Good skills coverage with some gaps."
    elif score >= 40:
        base = "Moderate skills alignment. Several key skills from the job description are missing."
    else:
        base = "Limited skills match. The skills section needs significant updates."

    parts = [base]
    if matched:
        parts.append(f"Matched: {', '.join(matched[:5])}.")
    if missing:
        parts.append(f"Missing: {', '.join(missing[:3])}.")
    return " ".join(parts)


def _build_experience_explanation(
    score: float, roles: List[str], impacts: int, bullets: int, actions: int
) -> str:
    if score >= 80:
        base = "Strong experience section with relevant roles and measurable impact."
    elif score >= 60:
        base = "Good experience section. Some improvements in quantification would help."
    elif score >= 40:
        base = "Moderate experience relevance. Consider highlighting impact and relevant keywords."
    else:
        base = "Experience section needs strengthening with action verbs and quantified results."

    parts = [base]
    if roles:
        parts.append(f"Detected roles: {', '.join(roles[:2])}.")
    parts.append(f"{impacts}/{bullets} bullets include quantified impact.")
    return " ".join(parts)


def _build_projects_explanation(
    score: float, matched_tech: List[str], all_skills: set,
    complexity: int, outcomes: int
) -> str:
    if score >= 80:
        base = "Excellent projects section showcasing relevant technology and impact."
    elif score >= 60:
        base = "Good projects with relevant tech stack. Adding outcomes would strengthen it."
    elif score >= 40:
        base = "Moderate project relevance. Consider highlighting technical complexity."
    else:
        base = "Projects section could better showcase relevant technologies and results."

    parts = [base]
    if matched_tech:
        parts.append(f"Matching tech: {', '.join(matched_tech[:3])}.")
    parts.append(f"{len(all_skills)} recognized tool(s), {complexity} complexity indicator(s), {outcomes} outcome(s).")
    return " ".join(parts)


def _build_education_explanation(
    score: float, field: Optional[str], level: Optional[str]
) -> str:
    if score >= 80:
        base = "Education aligns well with the role requirements."
    elif score >= 60:
        base = "Education provides a solid foundation for this role."
    elif score >= 40:
        base = "Education has moderate relevance. Certifications could strengthen this."
    else:
        base = "Education has limited direct relevance, but practical skills can compensate."

    parts = [base]
    if field and field != "general degree":
        parts.append(f"Field: {field.title()}.")
    if level and level != "degree detected":
        parts.append(f"Level: {level.title()}.")
    return " ".join(parts)


# ── Main Orchestrator ───────────────────────────────────────────────────────

def calculate_section_scores(
    resume_text: str,
    job_description: str,
    job_keywords: List[str],
) -> Dict:
    """
    Parse resume into sections and score each one independently.

    Returns dict suitable for SectionScores schema:
    {
        "skills": {score, explanation, matched_elements, missing_elements, weak_areas},
        "experience": {...},
        "projects": {...} or None,
        "education": {...}
    }
    """
    sections = parse_resume_sections(resume_text)

    # If resume is unstructured, try to score the whole text for each signal
    if "unstructured" in sections:
        full_text = sections["unstructured"]
        return {
            "skills": _score_skills(full_text, job_keywords, job_description),
            "experience": _score_experience(full_text, job_keywords, job_description),
            "projects": None,
            "education": _score_education(full_text, job_keywords, job_description),
        }

    skills_text = sections.get("skills", "")
    experience_text = sections.get("experience", "")
    projects_text = sections.get("projects", "")
    education_text = sections.get("education", "")

    return {
        "skills": _score_skills(skills_text, job_keywords, job_description),
        "experience": _score_experience(experience_text, job_keywords, job_description),
        "projects": _score_projects(projects_text, job_keywords, job_description) if projects_text else None,
        "education": _score_education(education_text, job_keywords, job_description),
    }
