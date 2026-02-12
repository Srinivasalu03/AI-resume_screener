"""
Unit tests for the ATS compatibility checker service.
"""

import pytest
from app.services.ats_checker import (
    check_ats_compatibility,
    _check_file_format,
    _check_section_headings,
    _check_required_sections,
    _check_contact_info,
    _check_parsing_characters,
    _check_bullet_structure,
    _check_resume_length,
    _check_date_formats,
    _check_tables_and_columns,
    _check_keyword_density,
    STATUS_PASS,
    STATUS_WARNING,
    STATUS_FAIL,
)


WELL_STRUCTURED_RESUME = (
    "John Doe\njohn.doe@email.com\n+1-555-123-4567\n\n"
    "Summary\n"
    "Experienced software engineer with 8+ years in backend development.\n\n"
    "Skills\n"
    "Python, FastAPI, Django, PostgreSQL, Docker, Kubernetes, AWS, Redis, Git, Linux\n\n"
    "Experience\n"
    "Senior Software Engineer at TechCorp (Jan 2020 - Present)\n"
    "- Developed scalable microservices using Python and FastAPI\n"
    "- Reduced API latency by 40% through caching optimizations\n"
    "- Deployed services on AWS using Docker and Kubernetes\n"
    "- Led team of 5 engineers to deliver major platform redesign\n"
    "- Improved test coverage from 45% to 92%\n"
    "- Implemented CI/CD pipeline automating deployment\n\n"
    "Software Engineer at StartupInc (Mar 2017 - Dec 2019)\n"
    "- Built RESTful APIs using Django and PostgreSQL\n"
    "- Managed database migrations for 10M+ records\n\n"
    "Education\n"
    "M.S. Computer Science, Stanford University, 2017"
)

POORLY_STRUCTURED_RESUME = (
    "just some text about my experience i worked at a company "
    "and did stuff with computers. i know python and javascript."
)


# ── File Format ──────────────────────────────────────────────────────────


class TestFileFormat:
    def test_pdf_passes(self):
        result = _check_file_format("resume.pdf")
        assert result["status"] == STATUS_PASS

    def test_docx_passes(self):
        result = _check_file_format("resume.docx")
        assert result["status"] == STATUS_PASS

    def test_txt_fails(self):
        result = _check_file_format("resume.txt")
        assert result["status"] == STATUS_FAIL

    def test_no_filename_passes(self):
        result = _check_file_format(None)
        assert result["status"] == STATUS_PASS


# ── Section Headings ─────────────────────────────────────────────────────


class TestSectionHeadings:
    def test_well_structured_passes(self):
        result = _check_section_headings(WELL_STRUCTURED_RESUME)
        assert result["status"] == STATUS_PASS

    def test_unstructured_fails(self):
        result = _check_section_headings(POORLY_STRUCTURED_RESUME)
        assert result["status"] == STATUS_FAIL

    def test_partial_structure_warns(self):
        partial = "Skills\nPython, Java\nSome other text without sections."
        result = _check_section_headings(partial)
        assert result["status"] in (STATUS_WARNING, STATUS_PASS)


# ── Required Sections ────────────────────────────────────────────────────


class TestRequiredSections:
    def test_all_present_passes(self):
        result = _check_required_sections(WELL_STRUCTURED_RESUME)
        assert result["status"] == STATUS_PASS

    def test_missing_one_warns(self):
        no_edu = "Skills\nPython\n\nExperience\n- Did stuff\n"
        result = _check_required_sections(no_edu)
        assert result["status"] == STATUS_WARNING

    def test_missing_multiple_fails(self):
        result = _check_required_sections(POORLY_STRUCTURED_RESUME)
        assert result["status"] in (STATUS_WARNING, STATUS_FAIL)


# ── Contact Info ─────────────────────────────────────────────────────────


class TestContactInfo:
    def test_both_present_passes(self):
        result = _check_contact_info(WELL_STRUCTURED_RESUME)
        assert result["status"] == STATUS_PASS

    def test_email_only_warns(self):
        result = _check_contact_info("john@email.com\nSummary\nDeveloper")
        assert result["status"] == STATUS_WARNING

    def test_nothing_fails(self):
        result = _check_contact_info("Summary\nDeveloper with experience")
        assert result["status"] == STATUS_FAIL


# ── Parsing Characters ──────────────────────────────────────────────────


class TestParsingCharacters:
    def test_clean_text_passes(self):
        result = _check_parsing_characters(WELL_STRUCTURED_RESUME)
        assert result["status"] == STATUS_PASS

    def test_many_special_chars_warns(self):
        text = "Skills: " + "".join([chr(i) for i in range(9728, 9750)]) * 2
        result = _check_parsing_characters(text)
        assert result["status"] in (STATUS_WARNING, STATUS_FAIL)


# ── Bullet Structure ────────────────────────────────────────────────────


class TestBulletStructure:
    def test_good_bullets_pass(self):
        result = _check_bullet_structure(WELL_STRUCTURED_RESUME)
        assert result["status"] == STATUS_PASS

    def test_no_bullets_warns(self):
        text = "I worked at a company.\nI did many things.\nI was a developer."
        result = _check_bullet_structure(text)
        assert result["status"] == STATUS_WARNING


# ── Resume Length ────────────────────────────────────────────────────────


class TestResumeLength:
    def test_good_length_passes(self):
        # Ensure a 200+ word resume passes
        extra = (
            "\n- Developed and maintained scalable distributed backend systems"
            "\n- Collaborated with cross functional teams on product development"
            "\n- Designed high availability architectures for mission critical services"
            "\n- Mentored junior engineers and conducted thorough code reviews"
            "\n- Implemented comprehensive monitoring and alerting dashboards"
        ) * 4
        result = _check_resume_length(WELL_STRUCTURED_RESUME + extra)
        assert result["status"] == STATUS_PASS

    def test_very_short_warns(self):
        result = _check_resume_length("Python developer experience")
        assert result["status"] == STATUS_WARNING

    def test_very_long_warns(self):
        long_text = "word " * 2000
        result = _check_resume_length(long_text)
        assert result["status"] == STATUS_WARNING


# ── Date Formats ─────────────────────────────────────────────────────────


class TestDateFormats:
    def test_standard_dates_pass(self):
        result = _check_date_formats(WELL_STRUCTURED_RESUME)
        assert result["status"] == STATUS_PASS

    def test_no_dates_warns(self):
        result = _check_date_formats("Python developer at a company doing stuff")
        assert result["status"] == STATUS_WARNING


# ── Tables and Columns ──────────────────────────────────────────────────


class TestTablesAndColumns:
    def test_clean_layout_passes(self):
        result = _check_tables_and_columns(WELL_STRUCTURED_RESUME)
        assert result["status"] == STATUS_PASS

    def test_pipe_tables_warn(self):
        text = "| Skill | Level |\n| Python | Expert |\n| Java | Good |\n| Docker | Advanced |"
        result = _check_tables_and_columns(text)
        assert result["status"] == STATUS_WARNING

    def test_heavy_tabs_warn(self):
        text = "\t".join(["col"] * 3) + "\n" + "\t".join(["col"] * 3) + "\n" * 5
        text = text * 5
        result = _check_tables_and_columns(text)
        assert result["status"] == STATUS_WARNING


# ── Keyword Density ──────────────────────────────────────────────────────


class TestKeywordDensity:
    def test_good_density_passes(self):
        result = _check_keyword_density(WELL_STRUCTURED_RESUME)
        assert result["status"] == STATUS_PASS

    def test_low_density_warns(self):
        text = "I was at a place. I did things. I was there for a while."
        result = _check_keyword_density(text)
        assert result["status"] == STATUS_WARNING


# ── Full Integration ─────────────────────────────────────────────────────


class TestFullATSCheck:
    def test_well_structured_high_score(self):
        result = check_ats_compatibility(WELL_STRUCTURED_RESUME, "resume.pdf")
        assert result["score"] >= 60
        assert result["pass_count"] > 0
        assert len(result["checks"]) == 10
        assert "summary" in result

    def test_poorly_structured_low_score(self):
        result = check_ats_compatibility(POORLY_STRUCTURED_RESUME)
        assert result["score"] < 80
        assert result["warning_count"] + result["fail_count"] > 0

    def test_all_checks_have_required_fields(self):
        result = check_ats_compatibility(WELL_STRUCTURED_RESUME)
        for check in result["checks"]:
            assert "name" in check
            assert "category" in check
            assert "status" in check
            assert check["status"] in (STATUS_PASS, STATUS_WARNING, STATUS_FAIL)
            assert "message" in check

    def test_score_within_range(self):
        result = check_ats_compatibility(WELL_STRUCTURED_RESUME)
        assert 0 <= result["score"] <= 100

    def test_counts_consistent(self):
        result = check_ats_compatibility(WELL_STRUCTURED_RESUME)
        total = result["pass_count"] + result["warning_count"] + result["fail_count"]
        assert total == len(result["checks"])
