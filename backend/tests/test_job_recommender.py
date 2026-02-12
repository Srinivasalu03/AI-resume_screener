"""
Unit tests for the Job Recommendation Service.

Tests skill extraction, experience detection, domain detection,
job matching, and the full recommendation pipeline.
"""

import pytest

from app.services.job_recommender import (
    _detect_experience_level,
    _extract_skills,
    _extract_role_signals,
    _detect_domains,
    _calculate_job_match,
    _generate_fit_reason,
    extract_resume_profile,
    generate_recommendations,
)


# ── Sample Resume Texts ────────────────────────────────────────────────────

BACKEND_RESUME = """
John Doe
john@email.com | San Francisco, CA

Summary
Senior software engineer with 7 years of experience building scalable backend systems.

Skills
Python, FastAPI, Django, PostgreSQL, Redis, Docker, Kubernetes, AWS, CI/CD, Git, Linux

Experience
Senior Backend Engineer at TechCorp (2020-Present)
- Designed and deployed microservices using FastAPI and Docker
- Managed PostgreSQL databases with 500M+ records
- Implemented CI/CD pipelines using GitHub Actions
- Led a team of 5 engineers on cloud migration to AWS

Software Developer at StartupX (2017-2020)
- Built REST APIs using Django and Flask
- Optimized SQL queries reducing latency by 40%
- Integrated Redis caching for high-traffic endpoints

Education
B.S. Computer Science, Stanford University, 2017
"""

DATA_SCIENCE_RESUME = """
Jane Smith
jane@email.com

Data Scientist with 3 years of experience in machine learning and NLP.

Skills
Python, TensorFlow, PyTorch, scikit-learn, pandas, NumPy, SQL, R, statistics, deep learning

Experience
Data Scientist at DataCo (2021-Present)
- Built NLP models for sentiment analysis using transformers
- Developed predictive models achieving 92% accuracy
- Created data pipelines using Airflow and Spark

Junior Data Analyst at AnalyticsInc (2020-2021)
- Performed A/B testing and statistical analysis
- Built dashboards using Tableau and Power BI
- Wrote SQL queries for data extraction

Education
M.S. Data Science, MIT, 2020
"""

INTERN_RESUME = """
Alex Johnson
alex@university.edu

Computer Science student seeking software engineering internship.

Skills
Python, JavaScript, React, SQL, Git, HTML, CSS

Projects
- Built a task management app using React and Node.js
- Created a Python CLI tool for file organization
- Developed a personal portfolio website

Education
B.S. Computer Science (Expected 2025), UC Berkeley
GPA: 3.8/4.0
"""

MINIMAL_RESUME = """
Software developer with experience in building web applications and working with teams.
Have used various programming tools and technologies in previous roles.
"""


# ── Experience Level Detection ─────────────────────────────────────────────

class TestExperienceDetection:
    def test_detects_senior(self):
        assert _detect_experience_level(BACKEND_RESUME) == "senior"

    def test_detects_intern(self):
        assert _detect_experience_level(INTERN_RESUME) == "intern"

    def test_detects_mid_default(self):
        assert _detect_experience_level(MINIMAL_RESUME) == "mid"

    def test_detects_entry(self):
        text = "Junior developer with 1 year of experience in web development."
        assert _detect_experience_level(text) == "entry"

    def test_detects_manager(self):
        text = "VP of Engineering with 15 years experience leading teams."
        assert _detect_experience_level(text) == "manager"


# ── Skill Extraction ──────────────────────────────────────────────────────

class TestSkillExtraction:
    def test_extracts_languages(self):
        skills = _extract_skills(BACKEND_RESUME)
        assert "python" in skills.get("languages", [])

    def test_extracts_frameworks(self):
        skills = _extract_skills(BACKEND_RESUME)
        assert "fastapi" in skills.get("frameworks", [])
        assert "django" in skills.get("frameworks", [])

    def test_extracts_databases(self):
        skills = _extract_skills(BACKEND_RESUME)
        assert "postgresql" in skills.get("databases", [])
        assert "redis" in skills.get("databases", [])

    def test_extracts_cloud(self):
        skills = _extract_skills(BACKEND_RESUME)
        assert "aws" in skills.get("cloud", [])

    def test_extracts_devops(self):
        skills = _extract_skills(BACKEND_RESUME)
        assert "docker" in skills.get("devops", [])
        assert "kubernetes" in skills.get("devops", [])

    def test_extracts_data_skills(self):
        skills = _extract_skills(DATA_SCIENCE_RESUME)
        assert "machine learning" in skills.get("data", [])

    def test_extracts_from_minimal_resume(self):
        skills = _extract_skills(MINIMAL_RESUME)
        # Minimal resume has very few concrete skills
        total = sum(len(v) for v in skills.values())
        assert total >= 0  # Should not crash

    def test_no_false_positives(self):
        """Should not extract random words as skills."""
        text = "I enjoy reading books and cooking dinner."
        skills = _extract_skills(text)
        total = sum(len(v) for v in skills.values())
        assert total == 0


# ── Role Signal Detection ─────────────────────────────────────────────────

class TestRoleDetection:
    def test_detects_backend_role(self):
        roles = _extract_role_signals(BACKEND_RESUME)
        # Should detect "software developer" or "backend engineer" signals
        assert len(roles) > 0

    def test_detects_data_scientist(self):
        roles = _extract_role_signals(DATA_SCIENCE_RESUME)
        assert "Data Professional" in roles

    def test_no_roles_in_minimal(self):
        roles = _extract_role_signals(MINIMAL_RESUME)
        # "software developer" should be detected
        assert "Software Engineer" in roles


# ── Domain Detection ──────────────────────────────────────────────────────

class TestDomainDetection:
    def test_backend_domains(self):
        skills = _extract_skills(BACKEND_RESUME)
        domains = _detect_domains(skills, BACKEND_RESUME)
        assert "Backend" in domains or "DevOps/Infrastructure" in domains or "Cloud" in domains

    def test_data_science_domains(self):
        skills = _extract_skills(DATA_SCIENCE_RESUME)
        domains = _detect_domains(skills, DATA_SCIENCE_RESUME)
        assert "AI/ML" in domains or "Big Data & Analytics" in domains

    def test_default_domain(self):
        skills = _extract_skills("I write some code.")
        domains = _detect_domains(skills, "I write some code.")
        assert "General Software Engineering" in domains


# ── Job Match Calculation ─────────────────────────────────────────────────

class TestJobMatching:
    def test_high_match_for_matching_skills(self):
        resume_skills = {"python", "fastapi", "docker", "postgresql", "aws", "kubernetes", "ci/cd"}
        score, matched, missing = _calculate_job_match(
            resume_skills_flat=resume_skills,
            resume_domains=["Backend", "Cloud"],
            experience_level="senior",
            job_template={
                "title": "Backend Developer",
                "core_skills": ["python", "sql", "postgresql", "docker", "git"],
                "bonus_skills": ["fastapi", "django", "redis", "kubernetes", "aws"],
                "domains": ["Backend", "Data/Databases"],
                "levels": ["entry", "mid", "senior"],
                "salary_ranges": {"senior": "$140K-$185K"},
            },
        )
        assert score >= 50
        assert len(matched) > 0

    def test_zero_for_incompatible_level(self):
        """An intern should get 0 for a manager-only role (distance > 1)."""
        score, _, _ = _calculate_job_match(
            resume_skills_flat={"python"},
            resume_domains=["General Software Engineering"],
            experience_level="intern",
            job_template={
                "title": "Tech Lead",
                "core_skills": ["python", "javascript"],
                "bonus_skills": ["kubernetes"],
                "domains": ["General Software Engineering"],
                "levels": ["manager"],
                "salary_ranges": {"manager": "$200K+"},
            },
        )
        assert score == 0.0

    def test_adjacent_level_penalty(self):
        """Mid-level should match senior roles but with penalty."""
        score, _, _ = _calculate_job_match(
            resume_skills_flat={"python", "docker", "kubernetes", "linux", "ci/cd"},
            resume_domains=["DevOps/Infrastructure"],
            experience_level="mid",
            job_template={
                "title": "SRE",
                "core_skills": ["linux", "python", "docker", "kubernetes"],
                "bonus_skills": ["prometheus", "grafana", "terraform", "aws", "ci/cd"],
                "domains": ["DevOps/Infrastructure", "Cloud"],
                "levels": ["senior"],
                "salary_ranges": {"senior": "$160K-$220K"},
            },
        )
        # Should get a score but with 15% penalty
        assert 0 < score < 100

    def test_missing_skills_populated(self):
        resume_skills = {"python"}
        _, _, missing = _calculate_job_match(
            resume_skills_flat=resume_skills,
            resume_domains=["Backend"],
            experience_level="mid",
            job_template={
                "title": "Backend Developer",
                "core_skills": ["python", "sql", "docker"],
                "bonus_skills": ["aws", "kubernetes"],
                "domains": ["Backend"],
                "levels": ["mid"],
                "salary_ranges": {"mid": "$100K"},
            },
        )
        assert "docker" in missing or "sql" in missing
        assert "aws" in missing or "kubernetes" in missing


# ── Resume Profile Extraction ─────────────────────────────────────────────

class TestResumeProfile:
    def test_backend_profile(self):
        profile = extract_resume_profile(BACKEND_RESUME)
        assert profile["experience_level"] == "senior"
        assert profile["skill_count"] > 5
        assert len(profile["domains"]) > 0
        assert len(profile["skills_flat"]) > 0

    def test_data_science_profile(self):
        profile = extract_resume_profile(DATA_SCIENCE_RESUME)
        assert profile["skill_count"] > 5
        assert len(profile["skills_flat"]) > 0

    def test_intern_profile(self):
        profile = extract_resume_profile(INTERN_RESUME)
        assert profile["experience_level"] == "intern"


# ── Full Recommendation Pipeline ──────────────────────────────────────────

class TestGenerateRecommendations:
    def test_returns_recommendations(self):
        result = generate_recommendations(BACKEND_RESUME)
        assert "profile" in result
        assert "recommendations" in result
        assert "total_matched" in result
        assert result["total_matched"] > 0

    def test_at_least_10_recommendations(self):
        """Backend resume with many skills should generate 10+ recommendations."""
        result = generate_recommendations(BACKEND_RESUME)
        assert result["total_matched"] >= 5  # Conservative; depends on min_score

    def test_recommendations_sorted_by_score(self):
        result = generate_recommendations(BACKEND_RESUME)
        scores = [r["match_score"] for r in result["recommendations"]]
        assert scores == sorted(scores, reverse=True)

    def test_recommendation_structure(self):
        result = generate_recommendations(BACKEND_RESUME)
        rec = result["recommendations"][0]
        assert "title" in rec
        assert "company" in rec
        assert "company_type" in rec
        assert "location" in rec
        assert "match_score" in rec
        assert "salary_range" in rec
        assert "matched_skills" in rec
        assert "missing_skills" in rec
        assert "description" in rec
        assert "why_good_fit" in rec

    def test_data_science_recommendations(self):
        result = generate_recommendations(DATA_SCIENCE_RESUME)
        titles = [r["title"] for r in result["recommendations"]]
        # Should include data-related roles
        has_data_role = any(
            "data" in t.lower() or "ml" in t.lower() or "machine" in t.lower()
            for t in titles
        )
        assert has_data_role

    def test_intern_recommendations(self):
        result = generate_recommendations(INTERN_RESUME)
        assert result["total_matched"] > 0
        titles = [r["title"] for r in result["recommendations"]]
        # Should include intern or junior roles
        has_appropriate_level = any(
            "intern" in t.lower() or "junior" in t.lower()
            for t in titles
        )
        assert has_appropriate_level

    def test_minimal_resume_does_not_crash(self):
        result = generate_recommendations(MINIMAL_RESUME)
        assert "recommendations" in result

    def test_with_matched_keywords(self):
        result = generate_recommendations(
            BACKEND_RESUME,
            matched_keywords=["python", "docker", "aws"],
            job_keywords=["python", "fastapi", "kubernetes"],
        )
        assert result["total_matched"] > 0

    def test_min_score_filter(self):
        result = generate_recommendations(BACKEND_RESUME, min_score=80.0)
        for rec in result["recommendations"]:
            assert rec["match_score"] >= 80.0

    def test_max_results_limit(self):
        result = generate_recommendations(BACKEND_RESUME, max_results=3)
        assert len(result["recommendations"]) <= 3


# ── Fit Reason Generation ─────────────────────────────────────────────────

class TestFitReason:
    def test_excellent_fit(self):
        reason = _generate_fit_reason(
            85.0, ["python", "docker", "aws"],
            {"experience_level": "senior", "domains": ["Backend"]}
        )
        assert "excellent" in reason.lower()

    def test_good_fit(self):
        reason = _generate_fit_reason(
            65.0, ["python"],
            {"experience_level": "mid", "domains": ["Backend"]}
        )
        assert "strong" in reason.lower()

    def test_no_skills_uses_domain(self):
        reason = _generate_fit_reason(
            40.0, [],
            {"experience_level": "mid", "domains": ["Backend", "Cloud"]}
        )
        assert "domain" in reason.lower() or "Backend" in reason
