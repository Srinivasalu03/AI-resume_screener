"""
AI Resume Screener - Main Application
FastAPI backend for matching resumes against job descriptions using NLP.
"""

import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models.schemas import (
    AnalysisResponse,
    ErrorResponse,
    HealthCheckResponse,
    create_success_response,
    create_error_response,
)
from app.services.pdf_parser import extract_text_from_pdf
from app.services.nlp_matcher import calculate_match_score
from app.services.explainer import generate_explanation

logger = logging.getLogger(__name__)

# ── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Resume Screener API",
    description="Match resumes to job descriptions using NLP (TF-IDF + cosine similarity)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Configuration ────────────────────────────────────────────────────────────

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {".pdf"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def validate_file(file: UploadFile) -> int:
    """Validate uploaded file type and size. Returns file size in bytes."""
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file_ext}'. Only PDF files are allowed.",
        )

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({file_size / (1024 * 1024):.1f} MB). Maximum is 5 MB.",
        )

    return file_size


def save_upload_file(upload_file: UploadFile) -> Path:
    """Save upload to a unique temp path to avoid filename collisions."""
    safe_name = f"{uuid.uuid4().hex}.pdf"
    file_path = UPLOAD_DIR / safe_name
    try:
        with file_path.open("wb") as f:
            while chunk := upload_file.file.read(8192):
                f.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    return file_path


def cleanup_file(file_path: Path) -> None:
    """Delete a temporary file, logging any failure."""
    try:
        if file_path and file_path.exists():
            file_path.unlink()
    except Exception as e:
        logger.warning("Failed to delete temp file %s: %s", file_path, e)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "message": "Welcome to AI Resume Screener API",
        "status": "running",
        "docs": "/docs",
        "endpoints": {"analyze": "/analyze", "health": "/health"},
    }


@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check for monitoring."""
    return HealthCheckResponse(
        status="healthy",
        upload_dir_exists=UPLOAD_DIR.exists(),
        max_file_size_mb=MAX_FILE_SIZE / (1024 * 1024),
        timestamp=datetime.now(timezone.utc),
    )


@app.post(
    "/analyze",
    response_model=AnalysisResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def analyze_resume(
    resume: UploadFile = File(..., description="Resume PDF file"),
    job_description: str = Form(..., description="Job description text"),
):
    """Analyze a resume against a job description and return a match score."""

    # ── Input validation ──
    job_description = job_description.strip()
    if len(job_description) < 10:
        raise HTTPException(
            status_code=400,
            detail="Job description must be at least 10 characters long.",
        )

    file_size = validate_file(resume)
    file_path = save_upload_file(resume)

    try:
        # Step 1: Extract text from PDF
        resume_text = extract_text_from_pdf(file_path)
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="Could not extract enough text from the PDF. It may be image-based or empty.",
            )

        # Step 2: Calculate match score via NLP
        score_data = calculate_match_score(resume_text, job_description)

        # Step 3: Generate human-readable explanation
        explanation = generate_explanation(
            resume_text=resume_text,
            job_description=job_description,
            score=score_data["score"],
            matched_keywords=score_data.get("matched_keywords", []),
            job_keywords=score_data.get("job_keywords", []),
        )

        # Step 4: Build and return response
        return create_success_response(
            score=score_data["score"],
            explanation=explanation,
            matched_keywords=score_data.get("matched_keywords", []),
            resume_word_count=len(resume_text.split()),
            job_word_count=len(job_description.split()),
            filename=resume.filename,
            file_size_kb=file_size / 1024,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")
    finally:
        cleanup_file(file_path)


# ── Dev Server ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
