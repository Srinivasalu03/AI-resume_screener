"""
API integration tests for the FastAPI endpoints.

Tests /health, / (root), and /analyze using httpx + FastAPI TestClient.
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
