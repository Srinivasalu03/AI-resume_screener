"""
Unit tests for the cover letter generation service.
"""

import pytest
from app.services.cover_letter_generator import (
    generate_cover_letter,
    _extract_name,
    _extract_achievements,
    _extract_target_role,
    _detect_primary_domain,
    _experience_to_phrase,
    _build_opening,
    _build_skills_paragraph,
    _build_closing,
)
from app.services.resume_rewriter import parse_resume_sections
from app.services.job_recommender import _extract_skills, _extract_role_signals


SAMPLE_RESUME = (
    "John Doe\njohn.doe@email.com\n+1-555-123-4567\n\n"
    "Summary\n"
    "Senior software engineer with 8 years of experience in backend development.\n\n"
    "Skills\n"
    "Python, FastAPI, Django, PostgreSQL, Docker, Kubernetes, AWS, Redis, Git, Linux\n\n"
    "Experience\n"
    "Senior Software Engineer at TechCorp (2020-Present)\n"
    "- Built scalable microservices using Python and FastAPI serving 1M+ requests/day\n"
    "- Reduced API latency by 40% through caching optimizations\n"
    "- Deployed services on AWS using Docker and Kubernetes\n"
    "- Led a team of 5 engineers to deliver 3 major releases\n\n"
    "Software Engineer at StartupInc (2017-2020)\n"
    "- Developed RESTful APIs using Django and PostgreSQL\n"
    "- Improved test coverage from 45% to 92%\n\n"
    "Education\n"
    "M.S. Computer Science, Stanford University, 2017"
)

SAMPLE_JD = (
    "Senior Python Developer\n"
    "We are looking for a Senior Python Developer with experience in FastAPI, "
    "Docker, AWS, and microservices architecture. The ideal candidate should have "
    "5+ years of experience building scalable backend systems."
)


class TestNameExtraction:
    def test_extracts_name_from_header(self):
        sections = parse_resume_sections(SAMPLE_RESUME)
        name = _extract_name(SAMPLE_RESUME, sections)
        assert name == "John Doe"

    def test_fallback_for_no_header(self):
        name = _extract_name("Some Resume Text", {})
        assert name == "Some Resume Text"

    def test_skips_email_lines(self):
        text = "john@email.com\nJane Smith\nSummary"
        sections = parse_resume_sections(text)
        name = _extract_name(text, sections)
        assert "email" not in name.lower()

    def test_placeholder_for_undetectable(self):
        text = "12345 67890 email@test.com http://url.com"
        name = _extract_name(text, {})
        assert name == "[Your Name]"


class TestAchievementExtraction:
    def test_finds_quantified_achievements(self):
        achievements = _extract_achievements(SAMPLE_RESUME)
        assert len(achievements) > 0
        assert any("40%" in a or "1M" in a for a in achievements)

    def test_no_achievements_in_plain_text(self):
        text = "I worked at a company and did some tasks."
        achievements = _extract_achievements(text)
        assert len(achievements) == 0

    def test_limits_to_5(self):
        text = "\n".join([
            f"- Improved metric {i} by {i*10}% through optimization"
            for i in range(1, 10)
        ])
        achievements = _extract_achievements(text)
        assert len(achievements) <= 5


class TestTargetRole:
    def test_extracts_role_from_jd(self):
        role = _extract_target_role(SAMPLE_JD, ["software_engineer"])
        assert len(role) > 0
        assert role != "the advertised"

    def test_fallback_to_role_signals(self):
        role = _extract_target_role("A company that does things", ["data_analyst"])
        assert "Analyst" in role or "Data" in role

    def test_fallback_to_generic(self):
        role = _extract_target_role("short jd", [])
        assert role == "the advertised"


class TestDomainDetection:
    def test_detects_backend_domain(self):
        skills = _extract_skills(SAMPLE_RESUME)
        domain = _detect_primary_domain(skills, SAMPLE_JD)
        assert "development" in domain.lower() or "engineering" in domain.lower() or "software" in domain.lower()

    def test_fallback_to_technology(self):
        domain = _detect_primary_domain({}, "a generic job description")
        assert domain == "technology"


class TestExperiencePhrase:
    def test_senior(self):
        assert "7" in _experience_to_phrase("senior") or "years" in _experience_to_phrase("senior")

    def test_junior(self):
        phrase = _experience_to_phrase("junior")
        assert phrase == "meaningful"

    def test_unknown(self):
        phrase = _experience_to_phrase("unknown_level")
        assert phrase == "solid"


class TestParagraphBuilders:
    def test_opening_has_role(self):
        opening = _build_opening("Python Developer", "5 years", "backend engineering")
        assert "Python Developer" in opening

    def test_skills_paragraph_lists_skills(self):
        skills_detected = _extract_skills(SAMPLE_RESUME)
        para = _build_skills_paragraph(
            ["python", "docker"], ["python", "docker", "aws"],
            skills_detected, "Developer"
        )
        assert "python" in para.lower() or "docker" in para.lower()

    def test_closing_is_professional(self):
        closing = _build_closing("software development")
        assert "opportunity" in closing.lower() or "discuss" in closing.lower() or "thank" in closing.lower()


class TestFullGeneration:
    def test_generates_cover_letter(self):
        result = generate_cover_letter(
            resume_text=SAMPLE_RESUME,
            job_description=SAMPLE_JD,
            matched_keywords=["python", "fastapi", "docker"],
            job_keywords=["python", "fastapi", "docker", "aws", "kubernetes"],
        )
        assert "cover_letter" in result
        assert result["word_count"] > 100
        assert "Dear Hiring Manager" in result["cover_letter"]
        assert "Sincerely" in result["cover_letter"]
        assert result["candidate_name"] == "John Doe"

    def test_word_count_reasonable(self):
        result = generate_cover_letter(
            resume_text=SAMPLE_RESUME,
            job_description=SAMPLE_JD,
        )
        assert 100 < result["word_count"] < 600

    def test_no_emojis(self):
        result = generate_cover_letter(
            resume_text=SAMPLE_RESUME,
            job_description=SAMPLE_JD,
        )
        import re
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001f900-\U0001f9FF]"
        )
        assert not emoji_pattern.search(result["cover_letter"])

    def test_key_highlights_populated(self):
        result = generate_cover_letter(
            resume_text=SAMPLE_RESUME,
            job_description=SAMPLE_JD,
            matched_keywords=["python", "docker"],
        )
        assert len(result["key_highlights"]) > 0

    def test_custom_name_override(self):
        result = generate_cover_letter(
            resume_text=SAMPLE_RESUME,
            job_description=SAMPLE_JD,
            candidate_name="Jane Smith",
        )
        assert result["candidate_name"] == "Jane Smith"
        assert "Jane Smith" in result["cover_letter"]

    def test_minimal_resume(self):
        """Should still generate even with minimal data."""
        result = generate_cover_letter(
            resume_text="Developer with experience in Python and web development. " * 5,
            job_description="Python developer needed for backend work.",
        )
        assert "cover_letter" in result
        assert result["word_count"] > 50
