"""
Tests for the NLP matching service.

Uses realistic resume and job description text to verify scoring
correctness, keyword extraction, and edge cases.
"""

import pytest
from app.services.nlp_matcher import (
    calculate_match_score,
    extract_keywords,
    preprocess_text,
)
from app.services.pdf_parser import clean_text


# ── Realistic test data ──────────────────────────────────────────────────────

PYTHON_BACKEND_JD = """
Senior Python Backend Developer

We are looking for a Senior Python Developer to join our engineering team.
You will design and build scalable REST APIs powering our SaaS platform.

Requirements:
- 5+ years of professional Python development
- Strong experience with FastAPI or Django REST Framework
- Proficiency with PostgreSQL and Redis
- Experience with Docker and Kubernetes for deployment
- Familiarity with CI/CD pipelines (GitHub Actions, Jenkins)
- Understanding of microservices architecture
- Experience with AWS services (EC2, S3, Lambda, RDS)
- Strong knowledge of Git and code review practices

Nice to have:
- Experience with message queues (RabbitMQ, Kafka)
- Knowledge of GraphQL
- Contributions to open source projects
"""

MATCHING_RESUME = """
John Smith - Senior Software Engineer

Summary:
Experienced Python developer with 7 years building production REST APIs
and microservices for high-traffic SaaS platforms.

Technical Skills:
Python, FastAPI, Django, Flask, PostgreSQL, MySQL, Redis, MongoDB,
Docker, Kubernetes, AWS (EC2, S3, Lambda, RDS, SQS), Git, GitHub Actions,
Jenkins, Terraform, Linux, RabbitMQ, GraphQL, gRPC

Experience:
Senior Backend Engineer | TechCorp | 2020-Present
- Designed and implemented RESTful APIs using FastAPI serving 10M+ requests/day
- Led migration from monolith to microservices architecture on AWS
- Set up CI/CD pipelines with GitHub Actions and Docker
- Managed PostgreSQL databases with Redis caching layer
- Deployed services on Kubernetes clusters

Backend Developer | StartupXYZ | 2017-2020
- Built Django REST APIs for the company's core product
- Implemented message queue processing with RabbitMQ
- Wrote comprehensive unit and integration tests
- Participated in code reviews and mentored junior developers

Education:
BS Computer Science | State University | 2017
"""

POOR_MATCH_RESUME = """
Sarah Johnson - Graphic Designer

Summary:
Creative graphic designer with 5 years of experience in branding,
print design, and digital media.

Skills:
Adobe Photoshop, Illustrator, InDesign, Figma, Sketch,
Typography, Color Theory, Brand Identity, Print Production,
Photography, Video Editing, After Effects

Experience:
Senior Graphic Designer | DesignStudio | 2019-Present
- Created brand identities for 50+ clients
- Designed marketing materials including brochures, posters, and banners
- Led a team of 3 junior designers
- Managed client relationships and project timelines

Junior Designer | CreativeAgency | 2017-2019
- Produced social media graphics and web banners
- Assisted with photo shoots and retouching
- Maintained brand consistency across all deliverables

Education:
BFA Graphic Design | Art Institute | 2017
"""

PARTIAL_MATCH_RESUME = """
Alex Chen - Full Stack Developer

Summary:
Full stack developer with 3 years of experience in web development
using JavaScript and Python.

Skills:
JavaScript, TypeScript, React, Node.js, Python, Flask, SQL,
MongoDB, HTML, CSS, Git, Docker, Heroku, AWS S3

Experience:
Full Stack Developer | WebCompany | 2021-Present
- Built React frontends with TypeScript
- Developed Flask REST APIs with PostgreSQL
- Deployed applications using Docker on Heroku
- Managed Git workflows and code reviews

Junior Developer | SmallStartup | 2020-2021
- Developed features for a Node.js backend
- Created responsive web pages with HTML and CSS
- Used Git for version control

Education:
BS Information Technology | Online University | 2020
"""


# ── Unit tests: preprocess_text ──────────────────────────────────────────────

class TestPreprocessText:
    def test_removes_stopwords(self):
        result = preprocess_text("the quick brown fox jumps over the lazy dog")
        assert "the" not in result.split()
        assert "over" not in result.split()
        assert "quick" in result.split()

    def test_empty_input(self):
        assert preprocess_text("") == ""

    def test_only_stopwords(self):
        result = preprocess_text("the a an is are was were")
        # Most or all should be removed
        assert len(result.split()) <= 1


# ── Unit tests: extract_keywords ─────────────────────────────────────────────

class TestExtractKeywords:
    def test_returns_list(self):
        keywords = extract_keywords(PYTHON_BACKEND_JD)
        assert isinstance(keywords, list)
        assert len(keywords) > 0

    def test_top_n_limit(self):
        keywords = extract_keywords(PYTHON_BACKEND_JD, top_n=5)
        assert len(keywords) <= 5

    def test_empty_input(self):
        assert extract_keywords("") == []

    def test_relevant_keywords_extracted(self):
        keywords = extract_keywords(PYTHON_BACKEND_JD, top_n=15)
        kw_text = " ".join(keywords).lower()
        # At least some of these domain terms should appear
        found = sum(1 for term in ["python", "docker", "aws", "api"]
                    if term in kw_text)
        assert found >= 2, f"Expected domain keywords, got: {keywords}"


# ── Integration tests: calculate_match_score ─────────────────────────────────

class TestCalculateMatchScore:
    def test_high_match_resume(self):
        """A highly relevant resume should score well above the low-match threshold."""
        result = calculate_match_score(MATCHING_RESUME, PYTHON_BACKEND_JD)
        assert result["score"] >= 40, f"Expected high score, got {result['score']}"
        assert len(result["matched_keywords"]) > 0
        assert len(result["job_keywords"]) > 0

    def test_low_match_resume(self):
        """A completely unrelated resume should score below 30."""
        result = calculate_match_score(POOR_MATCH_RESUME, PYTHON_BACKEND_JD)
        assert result["score"] < 30, f"Expected low score, got {result['score']}"

    def test_partial_match_resume(self):
        """A partially relevant resume should score between the extremes."""
        result = calculate_match_score(PARTIAL_MATCH_RESUME, PYTHON_BACKEND_JD)
        assert 15 < result["score"] < 80, f"Expected moderate score, got {result['score']}"

    def test_high_beats_low(self):
        """Matching resume should always score higher than non-matching."""
        high = calculate_match_score(MATCHING_RESUME, PYTHON_BACKEND_JD)
        low = calculate_match_score(POOR_MATCH_RESUME, PYTHON_BACKEND_JD)
        assert high["score"] > low["score"]

    def test_score_range(self):
        """Score should always be 0-100."""
        result = calculate_match_score(MATCHING_RESUME, PYTHON_BACKEND_JD)
        assert 0 <= result["score"] <= 100

    def test_identical_texts(self):
        """Identical texts should score very high."""
        result = calculate_match_score(PYTHON_BACKEND_JD, PYTHON_BACKEND_JD)
        assert result["score"] >= 80

    def test_empty_resume_returns_zero(self):
        """Empty resume text should yield a zero score."""
        result = calculate_match_score("", PYTHON_BACKEND_JD)
        assert result["score"] == 0.0

    def test_return_structure(self):
        """Returned dict must have the expected keys."""
        result = calculate_match_score(MATCHING_RESUME, PYTHON_BACKEND_JD)
        assert "score" in result
        assert "cosine_score" in result
        assert "matched_keywords" in result
        assert "job_keywords" in result


# ── Unit tests: clean_text ───────────────────────────────────────────────────

class TestCleanText:
    def test_lowercases(self):
        assert "hello" in clean_text("HELLO WORLD")

    def test_removes_emails(self):
        assert "@" not in clean_text("contact me at user@example.com today")

    def test_removes_urls(self):
        result = clean_text("visit https://example.com for more info")
        assert "https" not in result
        assert "example" not in result

    def test_removes_special_chars(self):
        result = clean_text("hello! @world #python $money")
        assert "!" not in result
        assert "#" not in result

    def test_removes_short_words(self):
        result = clean_text("I am a very good Python developer")
        assert "i " not in result  # single-char words removed
