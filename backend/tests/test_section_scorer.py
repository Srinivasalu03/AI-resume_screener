"""
Unit tests for the section scoring service.

Tests scoring logic for Skills, Experience, Projects, and Education sections.
"""

import pytest
from app.services.section_scorer import (
    _score_skills,
    _score_experience,
    _score_projects,
    _score_education,
    calculate_section_scores,
)


# ── Skills Scoring ──────────────────────────────────────────────────────────


class TestSkillsScoring:
    JOB_KEYWORDS = ["python", "fastapi", "docker", "kubernetes", "aws", "postgresql"]

    def test_high_match_skills(self):
        skills = "Python, FastAPI, Docker, Kubernetes, AWS, PostgreSQL, Redis, Git"
        result = _score_skills(skills, self.JOB_KEYWORDS, "Senior Python Developer")
        assert result["score"] is not None
        assert result["score"] >= 50
        assert len(result["matched_elements"]) > 0

    def test_low_match_skills(self):
        skills = "Java, Spring Boot, Maven"
        result = _score_skills(skills, self.JOB_KEYWORDS, "Senior Python Developer")
        assert result["score"] is not None
        assert result["score"] < 50
        assert len(result["missing_elements"]) > 0

    def test_missing_skills_detected(self):
        skills = "Python, Git"
        result = _score_skills(skills, self.JOB_KEYWORDS, "Python developer")
        missing = result["missing_elements"]
        assert any("docker" in m.lower() or "kubernetes" in m.lower() for m in missing)

    def test_empty_skills_section(self):
        result = _score_skills("", self.JOB_KEYWORDS, "Python developer")
        assert result["score"] is None
        assert "not found" in result["explanation"].lower()

    def test_none_skills_section(self):
        result = _score_skills(None, self.JOB_KEYWORDS, "Python developer")
        assert result["score"] is None

    def test_depth_indicators_boost_score(self):
        basic = "Python, Docker, AWS"
        advanced = "Advanced Python, Expert Docker, Certified AWS Solutions Architect"
        basic_result = _score_skills(basic, self.JOB_KEYWORDS, "Python developer")
        advanced_result = _score_skills(advanced, self.JOB_KEYWORDS, "Python developer")
        assert advanced_result["score"] >= basic_result["score"]

    def test_weak_areas_for_low_depth(self):
        skills = "Python Docker AWS"
        result = _score_skills(skills, self.JOB_KEYWORDS, "Python developer")
        assert any("proficiency" in w.lower() for w in result["weak_areas"])


# ── Experience Scoring ──────────────────────────────────────────────────────


class TestExperienceScoring:
    JOB_KEYWORDS = ["python", "fastapi", "microservices", "aws", "docker"]
    JOB_DESC = "Senior Python Developer building microservices with FastAPI"

    def test_strong_experience(self):
        exp = (
            "Senior Software Engineer at TechCorp\n"
            "- Built microservices using Python and FastAPI serving 1M+ requests/day\n"
            "- Reduced API latency by 40% through caching optimizations\n"
            "- Deployed services on AWS using Docker and Kubernetes\n"
            "- Led a team of 5 engineers to deliver 3 major releases"
        )
        result = _score_experience(exp, self.JOB_KEYWORDS, self.JOB_DESC)
        assert result["score"] is not None
        assert result["score"] >= 40
        assert len(result["matched_elements"]) > 0

    def test_weak_experience(self):
        exp = (
            "Intern at SmallCo\n"
            "- Helped with tasks\n"
            "- Attended meetings\n"
            "- Filed paperwork"
        )
        result = _score_experience(exp, self.JOB_KEYWORDS, self.JOB_DESC)
        assert result["score"] is not None
        assert result["score"] < 60
        assert len(result["weak_areas"]) > 0

    def test_impact_detection(self):
        exp = (
            "- Increased revenue by 25%\n"
            "- Reduced costs by $50K annually\n"
            "- Improved system uptime to 99.9%"
        )
        result = _score_experience(exp, self.JOB_KEYWORDS, self.JOB_DESC)
        assert any("impact" in m.lower() or "quantified" in m.lower() for m in result["matched_elements"])

    def test_no_experience_section(self):
        result = _score_experience("", self.JOB_KEYWORDS, self.JOB_DESC)
        assert result["score"] is None
        assert "not found" in result["explanation"].lower()

    def test_role_relevance(self):
        exp = "Software Engineer at Google\n- Developed backend services in Python"
        result = _score_experience(exp, self.JOB_KEYWORDS, self.JOB_DESC)
        assert result["score"] is not None

    def test_action_verb_weak_area(self):
        exp = (
            "- was responsible for coding\n"
            "- helped with database stuff\n"
            "- assisted in project work"
        )
        result = _score_experience(exp, self.JOB_KEYWORDS, self.JOB_DESC)
        assert any("action verb" in w.lower() for w in result["weak_areas"])


# ── Projects Scoring ────────────────────────────────────────────────────────


class TestProjectsScoring:
    JOB_KEYWORDS = ["python", "react", "docker", "postgresql", "api"]
    JOB_DESC = "Full-stack developer with Python and React"

    def test_strong_projects(self):
        proj = (
            "E-Commerce Platform\n"
            "- Built a scalable API using Python and FastAPI with PostgreSQL\n"
            "- Deployed to production with Docker, serving 10K+ users\n"
            "- Implemented React frontend with real-time updates\n"
            "- Published on GitHub with 500+ stars"
        )
        result = _score_projects(proj, self.JOB_KEYWORDS, self.JOB_DESC)
        assert result["score"] is not None
        assert result["score"] >= 40
        assert len(result["matched_elements"]) > 0

    def test_no_projects_returns_none(self):
        result = _score_projects("", self.JOB_KEYWORDS, self.JOB_DESC)
        assert result["score"] is None

    def test_tech_match_detection(self):
        proj = "Built a REST API with Python and Docker"
        result = _score_projects(proj, self.JOB_KEYWORDS, self.JOB_DESC)
        assert any("tech" in m.lower() for m in result["matched_elements"])

    def test_complexity_indicators(self):
        proj = "Built a distributed microservices platform handling millions of concurrent requests"
        result = _score_projects(proj, self.JOB_KEYWORDS, self.JOB_DESC)
        assert any("complexity" in m.lower() for m in result["matched_elements"])

    def test_weak_areas_for_simple_projects(self):
        proj = "Made a small app with Python"
        result = _score_projects(proj, self.JOB_KEYWORDS, self.JOB_DESC)
        assert len(result["weak_areas"]) > 0


# ── Education Scoring ───────────────────────────────────────────────────────


class TestEducationScoring:
    JOB_KEYWORDS = ["python", "machine learning"]
    JOB_DESC = "Machine Learning Engineer"

    def test_relevant_degree(self):
        edu = "M.S. Computer Science, Stanford University, 2020"
        result = _score_education(edu, self.JOB_KEYWORDS, self.JOB_DESC)
        assert result["score"] is not None
        assert result["score"] >= 60

    def test_less_relevant_degree(self):
        edu = "B.S. Business Administration, State University, 2019"
        result = _score_education(edu, self.JOB_KEYWORDS, self.JOB_DESC)
        assert result["score"] is not None
        assert result["score"] < 80

    def test_fair_baseline_scoring(self):
        """Any education should get at least 30 points."""
        edu = "Associate Degree in General Studies"
        result = _score_education(edu, self.JOB_KEYWORDS, self.JOB_DESC)
        assert result["score"] is not None
        assert result["score"] >= 30

    def test_no_education_returns_none(self):
        result = _score_education("", self.JOB_KEYWORDS, self.JOB_DESC)
        assert result["score"] is None

    def test_certifications_detected(self):
        edu = "B.S. Computer Science\nAWS Certified Solutions Architect"
        result = _score_education(edu, self.JOB_KEYWORDS, self.JOB_DESC)
        assert any("certification" in m.lower() or "aws" in m.lower() for m in result["matched_elements"])

    def test_phd_scores_higher_than_bachelors(self):
        phd = "Ph.D. Computer Science, MIT"
        bachelors = "B.S. Computer Science, State University"
        phd_result = _score_education(phd, self.JOB_KEYWORDS, self.JOB_DESC)
        bs_result = _score_education(bachelors, self.JOB_KEYWORDS, self.JOB_DESC)
        assert phd_result["score"] >= bs_result["score"]


# ── Integration: Full Resume Scoring ────────────────────────────────────────


class TestSectionScoresIntegration:
    FULL_RESUME = (
        "John Doe\njohn@email.com\n\n"
        "Summary\n"
        "Experienced software engineer with 7+ years in backend development.\n\n"
        "Skills\n"
        "Python, FastAPI, Django, PostgreSQL, Docker, Kubernetes, AWS, Redis, Git, Linux\n\n"
        "Experience\n"
        "Senior Software Engineer at TechCorp (2020-Present)\n"
        "- Built scalable microservices using Python and FastAPI\n"
        "- Reduced deployment time by 60% with CI/CD pipelines\n"
        "- Managed PostgreSQL databases with 50M+ records\n\n"
        "Projects\n"
        "Open Source API Gateway\n"
        "- Developed a high-performance API gateway in Python\n"
        "- Deployed on AWS with Docker, handling 100K requests/day\n"
        "- Published on GitHub with 200+ stars\n\n"
        "Education\n"
        "M.S. Computer Science, Stanford University, 2019"
    )

    JOB_KEYWORDS = ["python", "fastapi", "docker", "kubernetes", "aws", "postgresql"]
    JOB_DESC = "Senior Python Developer with FastAPI, Docker, AWS experience."

    def test_all_sections_scored(self):
        result = calculate_section_scores(self.FULL_RESUME, self.JOB_DESC, self.JOB_KEYWORDS)
        assert "skills" in result
        assert "experience" in result
        assert "projects" in result
        assert "education" in result

    def test_all_sections_have_scores(self):
        result = calculate_section_scores(self.FULL_RESUME, self.JOB_DESC, self.JOB_KEYWORDS)
        assert result["skills"]["score"] is not None
        assert result["experience"]["score"] is not None
        assert result["projects"]["score"] is not None
        assert result["education"]["score"] is not None

    def test_sections_have_explanations(self):
        result = calculate_section_scores(self.FULL_RESUME, self.JOB_DESC, self.JOB_KEYWORDS)
        for key in ["skills", "experience", "education"]:
            assert "explanation" in result[key]
            assert len(result[key]["explanation"]) > 0

    def test_resume_with_missing_projects(self):
        """Resume without projects section should return None for projects."""
        no_proj_resume = (
            "Skills\nPython, Docker, AWS\n\n"
            "Experience\nSoftware Engineer\n- Built APIs\n\n"
            "Education\nB.S. Computer Science"
        )
        result = calculate_section_scores(no_proj_resume, self.JOB_DESC, self.JOB_KEYWORDS)
        assert result["projects"] is None

    def test_unstructured_resume(self):
        """Unstructured resume should still be scored."""
        unstructured = (
            "Python developer with 5 years of experience building APIs "
            "using FastAPI and Docker. Worked at TechCorp on microservices. "
            "B.S. Computer Science from State University."
        )
        result = calculate_section_scores(unstructured, self.JOB_DESC, self.JOB_KEYWORDS)
        assert result["skills"]["score"] is not None
        assert result["experience"]["score"] is not None
        assert result["projects"] is None
        assert result["education"]["score"] is not None

    def test_scores_within_valid_range(self):
        result = calculate_section_scores(self.FULL_RESUME, self.JOB_DESC, self.JOB_KEYWORDS)
        for key in ["skills", "experience", "education"]:
            score = result[key]["score"]
            if score is not None:
                assert 0 <= score <= 100
        if result["projects"] is not None:
            assert 0 <= result["projects"]["score"] <= 100
