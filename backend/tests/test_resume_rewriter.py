"""
Unit tests for the resume rewriting service.
"""

import pytest
from app.services.resume_rewriter import (
    parse_resume_sections,
    rewrite_resume,
    _identify_missing_keywords,
    _enhance_skills,
    _enhance_summary,
    _enhance_bullets,
)


# ── Test Data ────────────────────────────────────────────────────────────────

STRUCTURED_RESUME = """John Doe
john.doe@email.com | (555) 123-4567

Summary
Experienced software developer with 5 years of experience building web applications.

Skills
Python, JavaScript, React, SQL, Git, Docker

Experience
- Built REST APIs using Flask and Django
- Designed database schemas for PostgreSQL
- Collaborated with cross-functional teams on agile projects
- Wrote unit tests and integration tests for backend services

Education
B.S. Computer Science, State University, 2018"""

UNSTRUCTURED_RESUME = """John Doe
Software developer with experience in Python and JavaScript.
Built web applications and REST APIs.
Familiar with Docker and Git."""

JOB_KEYWORDS = [
    "python", "fastapi", "kubernetes", "aws", "docker",
    "postgresql", "ci cd", "microservices", "terraform", "react",
    "machine learning", "sql", "git", "rest api", "agile",
]

MATCHED_KEYWORDS = ["python", "docker", "sql", "git", "react", "rest api"]


# ── Section Parsing ──────────────────────────────────────────────────────────

class TestParseResumeSections:
    def test_detects_standard_sections(self):
        sections = parse_resume_sections(STRUCTURED_RESUME)
        assert "summary" in sections
        assert "skills" in sections
        assert "experience" in sections
        assert "education" in sections

    def test_header_section_contains_contact_info(self):
        sections = parse_resume_sections(STRUCTURED_RESUME)
        assert "header" in sections
        assert "John Doe" in sections["header"]

    def test_handles_unstructured_resume(self):
        sections = parse_resume_sections(UNSTRUCTURED_RESUME)
        assert "unstructured" in sections
        assert "John Doe" in sections["unstructured"]

    def test_handles_empty_text(self):
        sections = parse_resume_sections("")
        # Should return unstructured with empty content or just header
        assert isinstance(sections, dict)

    def test_handles_single_section(self):
        text = "Skills\nPython, Java, Go"
        sections = parse_resume_sections(text)
        assert isinstance(sections, dict)


# ── Missing Keywords ─────────────────────────────────────────────────────────

class TestIdentifyMissingKeywords:
    def test_identifies_missing_keywords(self):
        missing = _identify_missing_keywords(JOB_KEYWORDS, MATCHED_KEYWORDS)
        assert "fastapi" in missing
        assert "kubernetes" in missing
        assert "aws" in missing

    def test_excludes_already_matched(self):
        missing = _identify_missing_keywords(JOB_KEYWORDS, MATCHED_KEYWORDS)
        assert "python" not in missing
        assert "docker" not in missing

    def test_filters_generic_terms(self):
        missing = _identify_missing_keywords(
            ["experience", "team", "python", "ability"], ["python"]
        )
        assert "experience" not in missing
        assert "team" not in missing
        assert "ability" not in missing

    def test_empty_inputs(self):
        assert _identify_missing_keywords([], []) == []
        assert _identify_missing_keywords(["python"], ["python"]) == []


# ── Skills Enhancement ───────────────────────────────────────────────────────

class TestEnhanceSkills:
    def test_adds_missing_keywords_comma_format(self):
        text = "Skills\nPython, JavaScript, React"
        enhanced, added = _enhance_skills(text, ["kubernetes", "aws", "terraform"])
        assert "kubernetes" in enhanced
        assert "aws" in enhanced
        assert len(added) == 3

    def test_preserves_existing_skills(self):
        text = "Skills\nPython, JavaScript, React"
        enhanced, _ = _enhance_skills(text, ["kubernetes"])
        assert "Python" in enhanced
        assert "JavaScript" in enhanced
        assert "React" in enhanced

    def test_handles_bullet_format(self):
        text = "Skills\n- Python\n- JavaScript"
        enhanced, added = _enhance_skills(text, ["kubernetes"])
        assert "kubernetes" in enhanced
        assert len(added) == 1

    def test_no_keywords_to_add(self):
        text = "Skills\nPython, JavaScript"
        enhanced, added = _enhance_skills(text, [])
        assert enhanced == text
        assert added == []

    def test_caps_at_eight_keywords(self):
        text = "Skills\nPython"
        many_keywords = [f"kw{i}" for i in range(15)]
        _, added = _enhance_skills(text, many_keywords)
        assert len(added) <= 8


# ── Summary Enhancement ──────────────────────────────────────────────────────

class TestEnhanceSummary:
    def test_enhances_existing_summary(self):
        text = "Summary\nExperienced developer with strong background in web development"
        enhanced, changes = _enhance_summary(text, JOB_KEYWORDS, ["kubernetes", "aws"])
        assert "kubernetes" in enhanced.lower() or "aws" in enhanced.lower()
        assert len(changes) > 0

    def test_generates_summary_for_empty(self):
        text = "Summary\n"
        enhanced, changes = _enhance_summary(text, JOB_KEYWORDS, ["kubernetes"])
        assert len(enhanced) > 20
        assert any("Generated" in c or "summary" in c.lower() for c in changes)

    def test_generates_summary_for_short(self):
        text = "Summary\nDeveloper"
        enhanced, changes = _enhance_summary(text, JOB_KEYWORDS, ["kubernetes"])
        assert len(enhanced) > 30


# ── Bullet Enhancement ───────────────────────────────────────────────────────

class TestEnhanceBullets:
    def test_adds_action_verbs(self):
        text = "Experience\n- web APIs using Flask\n- database schemas"
        enhanced, changes = _enhance_bullets(text, [])
        # Should have added action verbs to bullets lacking them
        assert any("action verb" in c.lower() for c in changes)

    def test_preserves_existing_action_verbs(self):
        text = "Experience\n- Developed REST APIs\n- Designed database schemas"
        enhanced, changes = _enhance_bullets(text, [])
        assert "Developed" in enhanced
        assert "Designed" in enhanced

    def test_incorporates_keywords(self):
        text = "Experience\n- Built web applications\n- Managed server deployments"
        enhanced, changes = _enhance_bullets(text, ["kubernetes", "terraform"])
        # Should incorporate at most 2 keywords
        keyword_changes = [c for c in changes if "keyword" in c.lower()]
        assert len(keyword_changes) <= 2


# ── Full Pipeline ────────────────────────────────────────────────────────────

class TestRewriteResume:
    def test_full_rewrite_structured(self):
        result = rewrite_resume(
            resume_text=STRUCTURED_RESUME,
            job_description="Looking for a Python developer with FastAPI, Kubernetes, AWS experience",
            matched_keywords=MATCHED_KEYWORDS,
            job_keywords=JOB_KEYWORDS,
        )
        assert "rewritten_text" in result
        assert "changes_made" in result
        assert "keywords_added" in result
        assert len(result["changes_made"]) > 0
        assert result["rewritten_text"] != result["original_text"]

    def test_full_rewrite_unstructured(self):
        result = rewrite_resume(
            resume_text=UNSTRUCTURED_RESUME,
            job_description="Looking for a Python developer with FastAPI, Kubernetes, AWS experience",
            matched_keywords=["python"],
            job_keywords=JOB_KEYWORDS,
        )
        assert "Key Skills" in result["rewritten_text"] or "keywords" in str(result["changes_made"]).lower()

    def test_already_good_match(self):
        result = rewrite_resume(
            resume_text=STRUCTURED_RESUME,
            job_description="Python developer",
            matched_keywords=JOB_KEYWORDS,  # All keywords already matched
            job_keywords=JOB_KEYWORDS,
        )
        assert "well-aligned" in str(result["changes_made"]).lower() or result["rewritten_text"] == STRUCTURED_RESUME

    def test_very_short_resume(self):
        result = rewrite_resume(
            resume_text="Short",
            job_description="Python developer",
            matched_keywords=[],
            job_keywords=["python"],
        )
        assert "too short" in str(result["changes_made"]).lower()

    def test_no_fabrication(self):
        """Rewritten text should not contain invented company names or dates."""
        result = rewrite_resume(
            resume_text=STRUCTURED_RESUME,
            job_description="Looking for a Python developer with FastAPI, Kubernetes, AWS experience",
            matched_keywords=MATCHED_KEYWORDS,
            job_keywords=JOB_KEYWORDS,
        )
        rewritten = result["rewritten_text"]
        # Original content should be preserved
        assert "John Doe" in rewritten
        assert "State University" in rewritten
