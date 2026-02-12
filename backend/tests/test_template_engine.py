"""
Unit tests for the role-based template engine.

Tests template configurations, bullet verb adjustment, summary tone adjustment,
and full template application.
"""

import pytest
from app.services.template_engine import (
    ROLE_TEMPLATES,
    get_available_templates,
    get_template,
    apply_template,
    _adjust_bullet_verbs,
    _adjust_summary_tone,
)


# ── Template Configuration ──────────────────────────────────────────────────


class TestTemplateConfigs:
    def test_all_four_templates_exist(self):
        assert "startup_tech" in ROLE_TEMPLATES
        assert "startup_non_tech" in ROLE_TEMPLATES
        assert "mnc_tech" in ROLE_TEMPLATES
        assert "mnc_non_tech" in ROLE_TEMPLATES

    def test_templates_have_required_keys(self):
        required_keys = {
            "name", "description", "icon", "action_verbs", "section_order",
            "bullet_style", "keyword_density", "summary_tone",
            "summary_template", "emphasis",
        }
        for name, config in ROLE_TEMPLATES.items():
            for key in required_keys:
                assert key in config, f"Template '{name}' missing key '{key}'"

    def test_action_verbs_not_empty(self):
        for name, config in ROLE_TEMPLATES.items():
            assert len(config["action_verbs"]) >= 10, f"Template '{name}' has too few verbs"

    def test_section_order_has_required_sections(self):
        for name, config in ROLE_TEMPLATES.items():
            order = config["section_order"]
            assert "header" in order
            assert "experience" in order
            assert "skills" in order

    def test_startup_tech_emphasizes_shipping(self):
        config = ROLE_TEMPLATES["startup_tech"]
        assert any("shipping" in e.lower() or "speed" in e.lower() for e in config["emphasis"])

    def test_mnc_non_tech_emphasizes_leadership(self):
        config = ROLE_TEMPLATES["mnc_non_tech"]
        assert any("leadership" in e.lower() for e in config["emphasis"])

    def test_get_available_templates_returns_all(self):
        templates = get_available_templates()
        assert len(templates) == 4
        ids = [t["id"] for t in templates]
        assert "startup_tech" in ids
        assert "mnc_tech" in ids

    def test_get_template_valid(self):
        config = get_template("startup_tech")
        assert config is not None
        assert config["name"] == "Startup Tech"

    def test_get_template_invalid(self):
        config = get_template("nonexistent")
        assert config is None


# ── Bullet Verb Adjustment ──────────────────────────────────────────────────


class TestBulletAdjustment:
    def test_replaces_generic_verbs(self):
        exp = "- Worked on building APIs\n- Helped with database design"
        verbs = ["Built", "Designed", "Shipped"]
        result, changes = _adjust_bullet_verbs(exp, verbs)
        assert "Worked on" not in result
        assert "Helped with" not in result
        assert len(changes) == 2

    def test_preserves_strong_verbs(self):
        exp = "- Developed a scalable API\n- Deployed microservices to AWS"
        verbs = ["Built", "Shipped"]
        result, changes = _adjust_bullet_verbs(exp, verbs)
        assert "Developed" in result
        assert "Deployed" in result
        assert len(changes) == 0

    def test_preserves_non_bullet_lines(self):
        exp = "Senior Engineer at TechCorp\n- Worked on APIs"
        verbs = ["Built"]
        result, changes = _adjust_bullet_verbs(exp, verbs)
        assert "Senior Engineer at TechCorp" in result

    def test_handles_various_bullet_styles(self):
        exp = "* Was responsible for testing\n\u2022 Participated in code reviews"
        verbs = ["Led", "Conducted"]
        result, changes = _adjust_bullet_verbs(exp, verbs)
        assert len(changes) == 2


# ── Summary Tone Adjustment ────────────────────────────────────────────────


class TestSummaryAdjustment:
    def test_generates_summary_for_empty(self):
        config = ROLE_TEMPLATES["startup_tech"]
        result, changes = _adjust_summary_tone("Summary\n", config, ["python", "fastapi"])
        assert len(result) > 20
        assert len(changes) > 0

    def test_enhances_existing_summary(self):
        config = ROLE_TEMPLATES["mnc_tech"]
        summary = "Summary\nExperienced engineer with 5 years building backend services."
        result, changes = _adjust_summary_tone(summary, config, ["python", "docker"])
        assert "Experienced engineer" in result
        assert len(changes) > 0

    def test_tone_matches_template(self):
        config = ROLE_TEMPLATES["startup_tech"]
        result, changes = _adjust_summary_tone("Summary\n", config, ["python"])
        assert any("innovative" in c.lower() for c in changes)

    def test_mnc_non_tech_leadership_tone(self):
        config = ROLE_TEMPLATES["mnc_non_tech"]
        result, changes = _adjust_summary_tone("Summary\n", config, ["management"])
        assert any("leadership" in c.lower() for c in changes)


# ── Full Template Application ───────────────────────────────────────────────


class TestTemplateApplication:
    SAMPLE_SECTIONS = {
        "header": "John Doe\njohn@email.com",
        "summary": "Summary\nSoftware developer with experience.",
        "skills": "Skills\nPython, JavaScript, Docker",
        "experience": (
            "Experience\n"
            "- Worked on building REST APIs\n"
            "- Helped with database migrations\n"
            "- Participated in code reviews"
        ),
        "education": "Education\nB.S. Computer Science",
    }

    def test_startup_tech_template_application(self):
        config = get_template("startup_tech")
        modified, changes = apply_template(
            self.SAMPLE_SECTIONS, config,
            job_keywords=["python", "fastapi", "aws"],
            missing_keywords=["fastapi", "aws"],
        )
        assert len(changes) > 0
        assert any("template" in c.lower() for c in changes)

    def test_mnc_tech_template_application(self):
        config = get_template("mnc_tech")
        modified, changes = apply_template(
            self.SAMPLE_SECTIONS, config,
            job_keywords=["java", "spring"],
            missing_keywords=["spring"],
        )
        assert len(changes) > 0

    def test_changes_made_populated(self):
        config = get_template("startup_non_tech")
        _, changes = apply_template(
            self.SAMPLE_SECTIONS, config,
            job_keywords=["marketing", "growth"],
            missing_keywords=["growth"],
        )
        # Should always have at least the "Applied template" change
        assert any("Applied" in c for c in changes)

    def test_experience_verbs_transformed(self):
        config = get_template("startup_tech")
        modified, changes = apply_template(
            self.SAMPLE_SECTIONS, config,
            job_keywords=["python"],
            missing_keywords=[],
        )
        # "Worked on" should be replaced
        assert "Worked on" not in modified.get("experience", "")

    def test_sections_preserved(self):
        config = get_template("mnc_non_tech")
        modified, _ = apply_template(
            self.SAMPLE_SECTIONS, config,
            job_keywords=[],
            missing_keywords=[],
        )
        # All original sections should still exist
        assert "header" in modified
        assert "skills" in modified
        assert "education" in modified
