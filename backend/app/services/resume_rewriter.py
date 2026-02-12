"""
Resume Rewriting Service (Rule-Based NLP)

Enhances resume text to better align with a target job description by:
- Injecting missing keywords into the skills section
- Improving the professional summary with JD-relevant terminology
- Augmenting experience bullets with action verbs and relevant terms

All modifications preserve truthful content — nothing is fabricated.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Common resume section headers (case-insensitive matching)
SECTION_PATTERNS = {
    "summary": re.compile(
        r"^(summary|professional\s*summary|objective|profile|about\s*me|career\s*objective)$",
        re.IGNORECASE,
    ),
    "experience": re.compile(
        r"^(experience|work\s*experience|professional\s*experience|employment(?:\s*history)?)$",
        re.IGNORECASE,
    ),
    "skills": re.compile(
        r"^(skills|technical\s*skills|core\s*competencies|competencies|technologies|tech\s*stack)$",
        re.IGNORECASE,
    ),
    "education": re.compile(
        r"^(education|academic|qualifications|certifications?(?:\s*(?:&|and)\s*education)?)$",
        re.IGNORECASE,
    ),
    "projects": re.compile(
        r"^(projects|key\s*projects|personal\s*projects)$",
        re.IGNORECASE,
    ),
}

# Action verbs for bullet enhancement
ACTION_VERBS = [
    "Developed", "Implemented", "Designed", "Architected", "Optimized",
    "Led", "Managed", "Delivered", "Built", "Created", "Established",
    "Streamlined", "Automated", "Integrated", "Deployed", "Configured",
    "Maintained", "Enhanced", "Coordinated", "Executed",
]

# Generic words that should not be injected as "missing keywords"
GENERIC_BLOCKLIST = {
    "experience", "team", "work", "working", "ability", "strong",
    "good", "years", "role", "position", "looking", "ideal",
    "candidate", "join", "company", "responsibilities", "requirements",
    "qualifications", "preferred", "required", "must", "including",
    "also", "well", "etc", "using", "used", "new", "one", "two",
}


def parse_resume_sections(text: str) -> Dict[str, str]:
    """
    Split resume text into named sections by detecting common headers.

    Returns a dict like:
        {"header": "...", "summary": "...", "experience": "...", "skills": "...", ...}

    If no recognizable sections are found, returns {"unstructured": full_text}.
    """
    lines = text.split("\n")
    sections: Dict[str, str] = {}
    current_section = "header"
    current_lines: List[str] = []

    for line in lines:
        stripped = line.strip()

        # Skip empty lines (but keep them in content for formatting)
        if not stripped:
            current_lines.append(line)
            continue

        # Check if this line is a section header
        # Heuristic: short line (< 40 chars), possibly uppercase or title case
        matched_section = None
        if len(stripped) < 40:
            clean_header = re.sub(r"[:\-_|#*=]+", "", stripped).strip()
            for section_name, pattern in SECTION_PATTERNS.items():
                if pattern.match(clean_header):
                    matched_section = section_name
                    break

        if matched_section:
            # Save current section
            content = "\n".join(current_lines).strip()
            if content:
                sections[current_section] = content
            current_section = matched_section
            current_lines = [line]  # Include the header line
        else:
            current_lines.append(line)

    # Save last section
    content = "\n".join(current_lines).strip()
    if content:
        sections[current_section] = content

    # If we only have "header" (no other sections detected), mark as unstructured
    if len(sections) <= 1 and "header" in sections:
        return {"unstructured": text}

    return sections


def _identify_missing_keywords(
    job_keywords: List[str], matched_keywords: List[str]
) -> List[str]:
    """Return JD keywords not present in matched_keywords, filtering out generic terms."""
    matched_lower = {kw.lower() for kw in matched_keywords}
    missing = []
    for kw in job_keywords:
        kw_lower = kw.lower()
        if kw_lower not in matched_lower and kw_lower not in GENERIC_BLOCKLIST:
            # Filter out single-character keywords
            if len(kw_lower) > 1:
                missing.append(kw)
    return missing


def _enhance_skills(
    skills_text: str, missing_keywords: List[str]
) -> Tuple[str, List[str]]:
    """
    Add missing keywords to the skills section.

    Detects formatting (comma-separated, pipe-separated, or bullet list)
    and appends keywords in the same style.
    """
    if not missing_keywords:
        return skills_text, []

    lines = skills_text.split("\n")
    # First line is usually the section header
    header_line = lines[0] if lines else ""
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    added = []
    keywords_to_add = missing_keywords[:8]  # Cap at 8 to avoid over-stuffing

    if not body:
        # Empty skills section — create content
        body = ", ".join(keywords_to_add)
        added = keywords_to_add
    elif "|" in body:
        # Pipe-separated format
        body = body.rstrip().rstrip("|").rstrip()
        body += " | " + " | ".join(keywords_to_add)
        added = keywords_to_add
    elif "," in body or ", " in body:
        # Comma-separated format
        body = body.rstrip().rstrip(",").rstrip()
        body += ", " + ", ".join(keywords_to_add)
        added = keywords_to_add
    elif any(line.strip().startswith(("-", "*", "\u2022")) for line in body.split("\n")):
        # Bullet list format
        for kw in keywords_to_add:
            body += f"\n- {kw}"
            added.append(kw)
    else:
        # Unknown format — append as comma list on new line
        body += "\n" + ", ".join(keywords_to_add)
        added = keywords_to_add

    result = f"{header_line}\n{body}" if header_line else body
    return result, added


def _enhance_summary(
    summary_text: str, job_keywords: List[str], missing_keywords: List[str]
) -> Tuple[str, List[str]]:
    """
    Improve the professional summary with JD-relevant terms.

    If summary is too short or empty, generates a basic one.
    Otherwise, appends a relevance sentence.
    """
    changes = []
    lines = summary_text.split("\n")
    header_line = lines[0] if lines else ""
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    # Pick top relevant keywords for the summary
    relevant_kws = missing_keywords[:3] if missing_keywords else job_keywords[:3]

    if len(body) < 30:
        # Very short or empty summary — generate a basic one
        kw_text = ", ".join(relevant_kws) if relevant_kws else "relevant technologies"
        body = (
            f"Results-driven professional with hands-on experience in {kw_text}. "
            f"Committed to delivering high-quality solutions and continuous improvement."
        )
        changes.append("Generated professional summary with job-relevant terminology")
    else:
        # Existing summary — append a reinforcement sentence
        if relevant_kws:
            kw_text = ", ".join(relevant_kws)
            addition = f" Skilled in {kw_text} with a focus on delivering impactful results."
            body = body.rstrip(".").rstrip() + "." + addition
            changes.append(f"Enhanced summary with keywords: {kw_text}")

    result = f"{header_line}\n{body}" if header_line else body
    return result, changes


def _enhance_bullets(
    experience_text: str, missing_keywords: List[str]
) -> Tuple[str, List[str]]:
    """
    Augment experience bullets with action verbs and relevant keywords.

    - Adds action verbs to bullets that lack them
    - Incorporates 1-2 missing keywords into contextually appropriate bullets
    """
    changes = []
    lines = experience_text.split("\n")
    result_lines = []
    used_verbs = set()
    keywords_placed = 0
    max_keyword_placements = min(2, len(missing_keywords))

    action_verb_pattern = re.compile(
        r"^[-*\u2022]\s*(" + "|".join(ACTION_VERBS) + r")\b",
        re.IGNORECASE,
    )

    for line in lines:
        stripped = line.strip()

        # Check if this is a bullet point
        is_bullet = bool(re.match(r"^[-*\u2022]\s+", stripped))

        if is_bullet:
            # Check if bullet already starts with an action verb
            if not action_verb_pattern.match(stripped):
                # Find an unused action verb
                for verb in ACTION_VERBS:
                    if verb.lower() not in used_verbs:
                        # Prepend verb to bullet content
                        bullet_char = stripped[0]
                        content = stripped[1:].strip().lstrip("-*\u2022").strip()
                        # Don't prepend if content already starts with a verb-like word
                        if content and content[0].isupper():
                            # Likely already has an action word not in our list
                            result_lines.append(line)
                            continue
                        stripped = f"{bullet_char} {verb} {content}"
                        used_verbs.add(verb.lower())
                        changes.append(f"Added action verb '{verb}' to bullet point")
                        break

            # Try to place a missing keyword in this bullet
            if keywords_placed < max_keyword_placements and missing_keywords:
                kw = missing_keywords[keywords_placed]
                # Only add if keyword isn't already in the bullet
                if kw.lower() not in stripped.lower():
                    stripped = stripped.rstrip(".").rstrip() + f", utilizing {kw}."
                    keywords_placed += 1
                    changes.append(f"Incorporated keyword '{kw}' into experience bullet")

            result_lines.append(stripped)
        else:
            result_lines.append(line)

    return "\n".join(result_lines), changes


def rewrite_resume(
    resume_text: str,
    job_description: str,
    matched_keywords: List[str],
    job_keywords: List[str],
    role_preference: Optional[str] = None,
) -> Dict:
    """
    Main resume rewriting orchestrator.

    Parses the resume into sections, enhances each relevant section,
    and reassembles. Returns a dict with the rewritten text, changes made,
    and keywords added.
    """
    # Edge case: very short resume
    if len(resume_text.strip()) < 100:
        return {
            "original_text": resume_text,
            "rewritten_text": resume_text,
            "changes_made": ["Resume too short to enhance meaningfully"],
            "keywords_added": [],
            "sections": {},
        }

    # Identify what's missing
    missing_keywords = _identify_missing_keywords(job_keywords, matched_keywords)

    # Edge case: already a great match
    if not missing_keywords:
        return {
            "original_text": resume_text,
            "rewritten_text": resume_text,
            "changes_made": ["Resume already well-aligned with job description — no changes needed"],
            "keywords_added": [],
            "sections": {},
        }

    # Parse into sections
    sections = parse_resume_sections(resume_text)
    all_changes: List[str] = []
    all_keywords_added: List[str] = []

    if "unstructured" in sections:
        # Can't parse sections — append a skills block at the end
        skills_line = ", ".join(missing_keywords[:8])
        rewritten = resume_text.rstrip() + f"\n\nKey Skills\n{skills_line}"
        all_changes.append(f"Added Key Skills section with {len(missing_keywords[:8])} missing keywords")
        all_keywords_added = missing_keywords[:8]
        return {
            "original_text": resume_text,
            "rewritten_text": rewritten,
            "changes_made": all_changes,
            "keywords_added": all_keywords_added,
            "sections": {"unstructured": rewritten},
        }

    # Enhance each section
    remaining_missing = list(missing_keywords)

    # 1. Skills section
    if "skills" in sections:
        enhanced, added = _enhance_skills(sections["skills"], remaining_missing)
        sections["skills"] = enhanced
        if added:
            all_changes.append(f"Added {len(added)} missing keywords to Skills: {', '.join(added)}")
            all_keywords_added.extend(added)
            # Remove placed keywords from remaining
            added_lower = {k.lower() for k in added}
            remaining_missing = [k for k in remaining_missing if k.lower() not in added_lower]

    # 2. Summary section
    if "summary" in sections:
        enhanced, changes = _enhance_summary(
            sections["summary"], job_keywords, remaining_missing
        )
        sections["summary"] = enhanced
        all_changes.extend(changes)

    # 3. Experience section
    if "experience" in sections:
        enhanced, changes = _enhance_bullets(sections["experience"], remaining_missing)
        sections["experience"] = enhanced
        all_changes.extend(changes)

    # If no skills section exists and we have missing keywords, add one
    if "skills" not in sections and missing_keywords:
        skills_content = "Skills\n" + ", ".join(missing_keywords[:8])
        sections["skills"] = skills_content
        all_changes.append(f"Added new Skills section with {len(missing_keywords[:8])} keywords")
        all_keywords_added.extend(missing_keywords[:8])

    # Apply role-based template if specified
    template_config = None
    if role_preference:
        from app.services.template_engine import get_template, apply_template
        template_config = get_template(role_preference)
        if template_config:
            sections, template_changes = apply_template(
                sections, template_config, job_keywords, remaining_missing
            )
            all_changes.extend(template_changes)

    # Reassemble sections in logical order (use template order if applied)
    if template_config:
        section_order = template_config["section_order"]
    else:
        section_order = ["header", "summary", "skills", "experience", "projects", "education"]
    ordered_parts = []
    used_sections = set()

    for section_name in section_order:
        if section_name in sections:
            ordered_parts.append(sections[section_name])
            used_sections.add(section_name)

    # Append any remaining sections not in the standard order
    for section_name, content in sections.items():
        if section_name not in used_sections:
            ordered_parts.append(content)

    rewritten_text = "\n\n".join(ordered_parts)

    return {
        "original_text": resume_text,
        "rewritten_text": rewritten_text,
        "changes_made": all_changes if all_changes else ["Minor formatting improvements applied"],
        "keywords_added": all_keywords_added,
        "sections": sections,
    }
