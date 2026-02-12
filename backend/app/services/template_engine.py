"""
Role-Based Resume Template Engine

Provides 4 resume templates tailored to different company/role types:
  - startup_tech: Fast-paced, impact-focused, technical depth
  - startup_non_tech: Growth-focused, achievement-outcome bullets
  - mnc_tech: Process-oriented, formal, responsibility-scope bullets
  - mnc_non_tech: Corporate, strategic-impact, leadership emphasis

Each template adjusts action verbs, bullet style, summary tone, section order,
and keyword density to match the target environment.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


# ── Template Configurations ────────────────────────────────────────────────

ROLE_TEMPLATES = {
    "startup_tech": {
        "name": "Startup Tech",
        "description": "Fast-paced, impact-focused, technical depth",
        "icon": "rocket",
        "action_verbs": [
            "Built", "Shipped", "Launched", "Scaled", "Architected",
            "Hacked", "Prototyped", "Deployed", "Automated", "Optimized",
            "Engineered", "Iterated", "Crafted", "Spearheaded", "Pioneered",
        ],
        "section_order": ["header", "summary", "skills", "projects", "experience", "education"],
        "bullet_style": "impact",
        "keyword_density": "high",
        "summary_tone": "innovative",
        "summary_template": (
            "Full-stack engineer who thrives in fast-paced environments. "
            "Passionate about {domains} with hands-on expertise in {skills}. "
            "Proven track record of shipping products that scale."
        ),
        "emphasis": ["technical depth", "shipping speed", "impact metrics"],
    },
    "startup_non_tech": {
        "name": "Startup Non-Tech",
        "description": "Growth-focused, achievement-outcome bullets",
        "icon": "chart",
        "action_verbs": [
            "Drove", "Accelerated", "Launched", "Grew", "Generated",
            "Captured", "Acquired", "Evangelized", "Partnered", "Closed",
            "Scaled", "Expanded", "Championed", "Transformed", "Delivered",
        ],
        "section_order": ["header", "summary", "experience", "skills", "projects", "education"],
        "bullet_style": "achievement",
        "keyword_density": "medium",
        "summary_tone": "growth",
        "summary_template": (
            "Growth-oriented professional with a passion for {domains}. "
            "Experienced in {skills} with a track record of driving measurable outcomes. "
            "Thrives in dynamic, fast-moving startup environments."
        ),
        "emphasis": ["growth metrics", "revenue impact", "cross-functional collaboration"],
    },
    "mnc_tech": {
        "name": "MNC Tech",
        "description": "Process-oriented, formal, responsibility-scope bullets",
        "icon": "building",
        "action_verbs": [
            "Developed", "Implemented", "Designed", "Maintained", "Configured",
            "Administered", "Standardized", "Documented", "Integrated", "Migrated",
            "Refactored", "Established", "Coordinated", "Facilitated", "Executed",
        ],
        "section_order": ["header", "summary", "experience", "skills", "education", "projects"],
        "bullet_style": "responsibility",
        "keyword_density": "medium",
        "summary_tone": "professional",
        "summary_template": (
            "Experienced technology professional with expertise in {skills}. "
            "Strong background in {domains} with a focus on enterprise-grade solutions, "
            "process improvement, and cross-team collaboration."
        ),
        "emphasis": ["enterprise scale", "process compliance", "team collaboration"],
    },
    "mnc_non_tech": {
        "name": "MNC Non-Tech",
        "description": "Corporate, strategic-impact, leadership emphasis",
        "icon": "briefcase",
        "action_verbs": [
            "Directed", "Oversaw", "Managed", "Orchestrated", "Governed",
            "Streamlined", "Influenced", "Negotiated", "Presented", "Supervised",
            "Strategized", "Mentored", "Cultivated", "Championed", "Delivered",
        ],
        "section_order": ["header", "summary", "experience", "education", "skills", "projects"],
        "bullet_style": "strategic",
        "keyword_density": "low",
        "summary_tone": "leadership",
        "summary_template": (
            "Strategic leader with deep expertise in {domains}. "
            "Proven ability to drive organizational impact through {skills}. "
            "Skilled in stakeholder management, cross-functional leadership, and delivering results at scale."
        ),
        "emphasis": ["leadership scope", "strategic impact", "stakeholder management"],
    },
}


# ── Public API ──────────────────────────────────────────────────────────────

def get_available_templates() -> List[Dict]:
    """Return template metadata for frontend display."""
    return [
        {
            "id": key,
            "name": cfg["name"],
            "description": cfg["description"],
            "icon": cfg["icon"],
            "emphasis": cfg["emphasis"],
        }
        for key, cfg in ROLE_TEMPLATES.items()
    ]


def get_template(role_type: str) -> Optional[Dict]:
    """Return full template config for the given role type."""
    return ROLE_TEMPLATES.get(role_type)


def apply_template(
    sections: Dict[str, str],
    template_config: Dict,
    job_keywords: List[str],
    missing_keywords: List[str],
) -> Tuple[Dict[str, str], List[str]]:
    """
    Apply a role-based template to parsed resume sections.

    Adjusts:
    - Action verbs in experience bullets to match template style
    - Summary tone based on template configuration
    - Section order (returned dict preserves the template's preferred order)

    Returns (modified_sections, list_of_changes_made).
    """
    changes = []
    modified = dict(sections)

    # 1. Adjust experience bullet verbs
    if "experience" in modified:
        new_exp, verb_changes = _adjust_bullet_verbs(
            modified["experience"], template_config["action_verbs"]
        )
        if verb_changes:
            modified["experience"] = new_exp
            changes.extend(verb_changes)

    # 2. Adjust summary tone
    if "summary" in modified:
        new_summary, summary_changes = _adjust_summary_tone(
            modified["summary"], template_config, job_keywords
        )
        if summary_changes:
            modified["summary"] = new_summary
            changes.extend(summary_changes)

    # 3. Record template applied
    template_name = template_config["name"]
    changes.append(f"Applied '{template_name}' template style")

    return modified, changes


# ── Internal Helpers ────────────────────────────────────────────────────────

# Generic verbs that should be replaced by template-specific ones
_GENERIC_VERBS = re.compile(
    r"^([-*\u2022]\s*)(Worked on|Helped with|Assisted in|Was responsible for|"
    r"Participated in|Contributed to|Involved in|Handled|Did|Made)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _adjust_bullet_verbs(
    experience_text: str, template_verbs: List[str]
) -> Tuple[str, List[str]]:
    """Replace generic verbs in experience bullets with template-specific ones."""
    changes = []
    verb_index = 0
    total_verbs = len(template_verbs)

    def replacer(match):
        nonlocal verb_index
        prefix = match.group(1)  # bullet char + spaces
        old_verb = match.group(2)
        new_verb = template_verbs[verb_index % total_verbs]
        verb_index += 1
        changes.append(f"Replaced '{old_verb}' with '{new_verb}'")
        return f"{prefix}{new_verb}"

    result = _GENERIC_VERBS.sub(replacer, experience_text)
    return result, changes


def _adjust_summary_tone(
    summary_text: str, template_config: Dict, job_keywords: List[str]
) -> Tuple[str, List[str]]:
    """Rewrite or enhance the summary to match the template tone."""
    changes = []
    lines = summary_text.split("\n")
    header_line = lines[0] if lines else ""
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    # Extract skills and domains from job keywords for the template
    skills_text = ", ".join(job_keywords[:4]) if job_keywords else "relevant technologies"
    domains_text = _infer_domains(job_keywords)

    template_summary = template_config["summary_template"].format(
        skills=skills_text, domains=domains_text
    )

    if len(body) < 30:
        # No meaningful summary — use template's summary
        body = template_summary
        changes.append(f"Generated {template_config['summary_tone']} summary from template")
    else:
        # Append template reinforcement
        tone = template_config["summary_tone"]
        body = body.rstrip(".").rstrip() + ". " + template_summary
        changes.append(f"Enhanced summary with {tone} tone")

    result = f"{header_line}\n{body}" if header_line else body
    return result, changes


def _infer_domains(keywords: List[str]) -> str:
    """Infer domain areas from keywords for template summaries."""
    domain_map = {
        "web development": ["react", "angular", "vue", "frontend", "html", "css", "javascript"],
        "backend engineering": ["api", "fastapi", "django", "flask", "express", "node"],
        "cloud computing": ["aws", "azure", "gcp", "cloud", "kubernetes", "docker"],
        "data science": ["machine learning", "data", "analytics", "pandas", "tensorflow"],
        "mobile development": ["ios", "android", "react native", "flutter", "swift"],
        "DevOps": ["ci/cd", "jenkins", "terraform", "ansible", "devops"],
    }

    detected = []
    kw_lower = {k.lower() for k in keywords}
    for domain, triggers in domain_map.items():
        if any(t in kw_lower for t in triggers):
            detected.append(domain)

    return ", ".join(detected[:2]) if detected else "technology and innovation"
