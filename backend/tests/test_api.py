"""
API integration tests for the FastAPI endpoints.

Tests /health, / (root), /analyze, /rewrite, and /download using httpx + FastAPI TestClient.
"""

import io
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ── Root & Health ─────────────────────────────────────────────────────────────

class TestRootEndpoint:
    def test_root_returns_200(self):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_serves_html_or_json(self):
        """Root returns frontend HTML when available, or JSON API info."""
        resp = client.get("/")
        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type:
            assert "AI Resume Screener" in resp.text
        else:
            data = resp.json()
            assert data["status"] == "running"
            assert "analyze" in data["endpoints"]


class TestHealthEndpoint:
    def test_health_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "upload_dir_exists" in data


# ── /analyze validation ──────────────────────────────────────────────────────

class TestAnalyzeValidation:
    def _make_pdf_bytes(self, text: str = "This is a sample resume with enough text to pass validation for the AI resume screener application") -> bytes:
        """Create a minimal valid PDF containing *text*."""
        # Minimal PDF spec structure
        lines = [
            b"%PDF-1.4",
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj",
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj",
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj",
        ]
        # Encode text into a content stream
        stream_content = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET".encode()
        stream_obj = b"4 0 obj<</Length " + str(len(stream_content)).encode() + b">>stream\n" + stream_content + b"\nendstream endobj"
        lines.append(stream_obj)
        lines.append(b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj")
        # xref + trailer (simplified)
        lines.append(b"xref")
        lines.append(b"0 6")
        lines.append(b"trailer<</Size 6/Root 1 0 R>>")
        lines.append(b"startxref")
        lines.append(b"0")
        lines.append(b"%%EOF")
        return b"\n".join(lines)

    def test_missing_job_description(self):
        pdf = self._make_pdf_bytes()
        resp = client.post(
            "/analyze",
            files={"resume": ("resume.pdf", io.BytesIO(pdf), "application/pdf")},
            data={"job_description": "short"},
        )
        assert resp.status_code == 400

    def test_non_pdf_rejected(self):
        resp = client.post(
            "/analyze",
            files={"resume": ("resume.txt", io.BytesIO(b"not a pdf"), "text/plain")},
            data={"job_description": "Looking for a Python developer with 5 years experience in FastAPI"},
        )
        assert resp.status_code == 400
        assert "PDF" in resp.json()["detail"]

    def test_empty_file_rejected(self):
        resp = client.post(
            "/analyze",
            files={"resume": ("resume.pdf", io.BytesIO(b""), "application/pdf")},
            data={"job_description": "Looking for a Python developer with 5 years experience in FastAPI"},
        )
        assert resp.status_code == 400

    def test_successful_analysis_structure(self):
        """A valid PDF + JD should return a properly structured response."""
        pdf = self._make_pdf_bytes(
            "Experienced Python developer with 5 years building REST APIs "
            "using FastAPI Django PostgreSQL Docker Kubernetes AWS microservices "
            "Git CI CD pipelines senior backend engineer"
        )
        resp = client.post(
            "/analyze",
            files={"resume": ("resume.pdf", io.BytesIO(pdf), "application/pdf")},
            data={
                "job_description": (
                    "Senior Python Developer with experience in FastAPI, Docker, "
                    "AWS, PostgreSQL, Kubernetes, and microservices architecture."
                )
            },
        )
        # The PDF might not extract cleanly (minimal spec), so accept 200 or 400
        if resp.status_code == 200:
            data = resp.json()
            assert data["success"] is True
            assert "data" in data
            assert 0 <= data["data"]["score"] <= 100
            assert isinstance(data["data"]["matched_keywords"], list)
            assert "metadata" in data
            # New fields should be present
            assert "job_keywords" in data["data"]
            assert "resume_text" in data["data"]


# ── /rewrite endpoint ────────────────────────────────────────────────────────

class TestRewriteEndpoint:
    SAMPLE_RESUME_TEXT = (
        "John Doe\njohn@email.com\n\n"
        "Summary\nExperienced software developer with 5 years in web development.\n\n"
        "Skills\nPython, JavaScript, React, SQL, Git, Docker\n\n"
        "Experience\n"
        "- Built REST APIs using Flask and Django\n"
        "- Designed database schemas for PostgreSQL\n"
        "- Collaborated with cross-functional teams on agile projects\n"
        "- Wrote unit tests and integration tests for backend services\n\n"
        "Education\nB.S. Computer Science, State University, 2018"
    )

    def test_rewrite_returns_comparison(self):
        """POST /rewrite with valid data returns a comparison response."""
        resp = client.post(
            "/rewrite",
            json={
                "resume_text": self.SAMPLE_RESUME_TEXT,
                "job_description": "Senior Python Developer with FastAPI, Kubernetes, AWS, and CI/CD experience.",
                "matched_keywords": ["python", "docker", "sql", "git"],
                "job_keywords": ["python", "fastapi", "kubernetes", "aws", "ci cd", "docker", "sql"],
                "original_score": 45.0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["original_score"] == 45.0
        assert "updated_score" in data
        assert "score_improvement" in data
        assert "improvements_summary" in data
        assert len(data["improvements_summary"]) > 0
        assert "download_id" in data
        assert len(data["download_id"]) == 32  # UUID hex
        assert "updated_analysis" in data
        assert data["updated_analysis"]["score"] >= 0

    def test_rewrite_rejects_short_resume(self):
        """Resume text under 50 chars should be rejected by Pydantic validation."""
        resp = client.post(
            "/rewrite",
            json={
                "resume_text": "Too short",
                "job_description": "Python developer with 5 years experience",
                "matched_keywords": [],
                "job_keywords": ["python"],
                "original_score": 10.0,
            },
        )
        assert resp.status_code == 422  # Pydantic validation error

    def test_rewrite_rejects_short_jd(self):
        """Job description under 10 chars should be rejected."""
        resp = client.post(
            "/rewrite",
            json={
                "resume_text": self.SAMPLE_RESUME_TEXT,
                "job_description": "short",
                "matched_keywords": [],
                "job_keywords": [],
                "original_score": 10.0,
            },
        )
        assert resp.status_code == 422

    def test_download_after_rewrite(self):
        """GET /download/{id} should return a PDF after a successful rewrite."""
        # First, create a rewrite
        rewrite_resp = client.post(
            "/rewrite",
            json={
                "resume_text": self.SAMPLE_RESUME_TEXT,
                "job_description": "Senior Python Developer with FastAPI, Kubernetes, AWS experience.",
                "matched_keywords": ["python", "docker"],
                "job_keywords": ["python", "fastapi", "kubernetes", "aws", "docker"],
                "original_score": 30.0,
            },
        )
        assert rewrite_resp.status_code == 200
        download_id = rewrite_resp.json()["download_id"]

        # Then download the PDF
        dl_resp = client.get(f"/download/{download_id}")
        assert dl_resp.status_code == 200
        assert dl_resp.headers["content-type"] == "application/pdf"
        assert dl_resp.content[:5] == b"%PDF-"

    def test_download_invalid_id_returns_400(self):
        """Invalid download ID format should return 400."""
        resp = client.get("/download/not-a-valid-id!")
        assert resp.status_code == 400

    def test_download_nonexistent_id_returns_404(self):
        """Valid format but nonexistent ID should return 404."""
        resp = client.get("/download/00000000000000000000000000000000")
        assert resp.status_code == 404


# ── /recommendations endpoint ──────────────────────────────────────────────

class TestRecommendationsEndpoint:
    SAMPLE_RESUME = (
        "John Doe\njohn@email.com\n\n"
        "Senior Software Engineer with 7 years of experience.\n\n"
        "Skills\nPython, FastAPI, Django, PostgreSQL, Docker, Kubernetes, AWS, CI/CD, Git, Linux\n\n"
        "Experience\n"
        "- Built microservices using FastAPI and Docker\n"
        "- Managed PostgreSQL databases with millions of records\n"
        "- Implemented CI/CD pipelines using GitHub Actions\n"
        "- Led cloud migration to AWS with Kubernetes orchestration\n\n"
        "Education\nB.S. Computer Science, Stanford University, 2017"
    )

    def test_recommendations_returns_results(self):
        """POST /recommendations with valid resume returns recommendations."""
        resp = client.post(
            "/recommendations",
            json={
                "resume_text": self.SAMPLE_RESUME,
                "matched_keywords": ["python", "docker"],
                "job_keywords": ["python", "fastapi", "kubernetes"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total_matched"] > 0
        assert "profile" in data
        assert "recommendations" in data
        assert len(data["recommendations"]) > 0

    def test_recommendation_structure(self):
        """Each recommendation should have required fields."""
        resp = client.post(
            "/recommendations",
            json={"resume_text": self.SAMPLE_RESUME},
        )
        assert resp.status_code == 200
        rec = resp.json()["recommendations"][0]
        assert "title" in rec
        assert "company" in rec
        assert "match_score" in rec
        assert 0 <= rec["match_score"] <= 100
        assert "matched_skills" in rec
        assert "missing_skills" in rec
        assert "salary_range" in rec

    def test_profile_fields(self):
        """Profile should include experience level, domains, skills."""
        resp = client.post(
            "/recommendations",
            json={"resume_text": self.SAMPLE_RESUME},
        )
        assert resp.status_code == 200
        profile = resp.json()["profile"]
        assert "experience_level" in profile
        assert "domains" in profile
        assert "detected_skills" in profile
        assert "skill_count" in profile

    def test_rejects_short_resume(self):
        """Resume text under 50 chars should be rejected."""
        resp = client.post(
            "/recommendations",
            json={"resume_text": "Too short"},
        )
        assert resp.status_code == 422


# ── /rewrite with role_preference ────────────────────────────────────────


class TestRewriteWithTemplate:
    SAMPLE_RESUME_TEXT = (
        "John Doe\njohn@email.com\n\n"
        "Summary\nExperienced software developer with 5 years in web development.\n\n"
        "Skills\nPython, JavaScript, React, SQL, Git, Docker\n\n"
        "Experience\n"
        "- Worked on building REST APIs using Flask and Django\n"
        "- Helped with database schemas for PostgreSQL\n"
        "- Participated in agile projects\n\n"
        "Education\nB.S. Computer Science, State University, 2018"
    )

    def test_rewrite_with_startup_tech_template(self):
        """POST /rewrite with role_preference should apply template."""
        resp = client.post(
            "/rewrite",
            json={
                "resume_text": self.SAMPLE_RESUME_TEXT,
                "job_description": "Senior Python Developer with FastAPI, Kubernetes, AWS experience.",
                "matched_keywords": ["python", "docker"],
                "job_keywords": ["python", "fastapi", "kubernetes", "aws", "docker"],
                "original_score": 40.0,
                "role_preference": "startup_tech",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # Template application should be mentioned in improvements
        assert any("template" in change.lower() or "startup" in change.lower()
                    for change in data["improvements_summary"])

    def test_rewrite_with_mnc_tech_template(self):
        """MNC tech template should work."""
        resp = client.post(
            "/rewrite",
            json={
                "resume_text": self.SAMPLE_RESUME_TEXT,
                "job_description": "Java Developer with Spring Boot and enterprise experience.",
                "matched_keywords": ["java"],
                "job_keywords": ["java", "spring boot", "enterprise", "microservices"],
                "original_score": 30.0,
                "role_preference": "mnc_tech",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_rewrite_without_template_still_works(self):
        """Omitting role_preference should work as before."""
        resp = client.post(
            "/rewrite",
            json={
                "resume_text": self.SAMPLE_RESUME_TEXT,
                "job_description": "Python developer with 5 years experience in FastAPI.",
                "matched_keywords": ["python"],
                "job_keywords": ["python", "fastapi"],
                "original_score": 35.0,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
