"""
AI Resume Screener - Main Application
FastAPI backend for matching resumes against job descriptions using NLP.
"""

import re
import time
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.models.schemas import (
    AnalysisResponse,
    HealthCheckResponse,
    MatchData,
    RewriteRequest,
    RewriteResponse,
    create_success_response,
)
from app.services.pdf_parser import extract_text_from_pdf
from app.services.nlp_matcher import calculate_match_score
from app.services.explainer import generate_explanation
from app.services.resume_rewriter import rewrite_resume
from app.services.pdf_generator import generate_resume_pdf

logger = logging.getLogger(__name__)

# ── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Resume Screener API",
    description="Match resumes to job descriptions using NLP (TF-IDF + cosine similarity)",
    version="2.0.0",
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

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {".pdf"}
DOWNLOAD_MAX_AGE = 3600  # 1 hour TTL for generated PDFs


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


def _cleanup_old_downloads() -> None:
    """Delete generated PDFs older than DOWNLOAD_MAX_AGE seconds."""
    for f in DOWNLOAD_DIR.glob("*.pdf"):
        try:
            if time.time() - f.stat().st_mtime > DOWNLOAD_MAX_AGE:
                f.unlink()
                logger.info("Cleaned up stale download: %s", f.name)
        except Exception as e:
            logger.warning("Cleanup failed for %s: %s", f, e)


# ── Endpoints ────────────────────────────────────────────────────────────────

# ── Frontend static files (production: serve frontend from backend) ──────────
# In Docker: frontend is at /app/frontend/ (sibling to app/ package)
# In local dev: frontend is at ../../frontend relative to this file

_this_dir = Path(__file__).resolve().parent  # backend/app/
FRONTEND_DIR = _this_dir.parent / "frontend"  # backend/frontend (Docker)
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = _this_dir.parent.parent / "frontend"  # local dev: project_root/frontend


@app.on_event("startup")
async def startup_event():
    """Clean up stale download files from previous runs."""
    _cleanup_old_downloads()


@app.get("/")
async def root():
    """Serve frontend index.html if available, otherwise return API info."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "message": "Welcome to AI Resume Screener API",
        "status": "running",
        "docs": "/docs",
        "endpoints": {"analyze": "/analyze", "health": "/health", "rewrite": "/rewrite"},
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
            score=score_data["score"],
            matched_keywords=score_data.get("matched_keywords", []),
            job_keywords=score_data.get("job_keywords", []),
        )

        # Step 4: Build and return response (now includes resume_text and job_keywords)
        return create_success_response(
            score=score_data["score"],
            explanation=explanation,
            matched_keywords=score_data.get("matched_keywords", []),
            resume_word_count=len(resume_text.split()),
            job_word_count=len(job_description.split()),
            filename=resume.filename,
            file_size_kb=file_size / 1024,
            resume_text=resume_text,
            job_keywords=score_data.get("job_keywords", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")
    finally:
        cleanup_file(file_path)


@app.post("/rewrite", response_model=RewriteResponse)
async def rewrite_resume_endpoint(request: RewriteRequest):
    """Rewrite resume to better match job description and return comparison."""
    try:
        # Step 1: Rewrite resume using rule-based NLP
        rewrite_result = rewrite_resume(
            resume_text=request.resume_text,
            job_description=request.job_description,
            matched_keywords=request.matched_keywords,
            job_keywords=request.job_keywords,
        )

        # Step 2: Re-run analysis on rewritten text
        new_score_data = calculate_match_score(
            rewrite_result["rewritten_text"],
            request.job_description,
        )
        new_explanation = generate_explanation(
            score=new_score_data["score"],
            matched_keywords=new_score_data.get("matched_keywords", []),
            job_keywords=new_score_data.get("job_keywords", []),
        )

        # Step 3: Generate downloadable PDF
        download_id = uuid.uuid4().hex
        pdf_path = DOWNLOAD_DIR / f"{download_id}.pdf"
        generate_resume_pdf(
            resume_text=rewrite_result["rewritten_text"],
            sections=rewrite_result.get("sections", {}),
            output_path=pdf_path,
        )

        # Step 4: Build comparison response
        updated_score = new_score_data["score"]
        return RewriteResponse(
            success=True,
            original_score=request.original_score,
            updated_score=round(updated_score, 2),
            score_improvement=round(updated_score - request.original_score, 2),
            improvements_summary=rewrite_result["changes_made"],
            rewritten_resume_preview=rewrite_result["rewritten_text"][:500],
            download_id=download_id,
            updated_analysis=MatchData(
                score=round(updated_score, 2),
                match_percentage=f"{round(updated_score, 1)}%",
                explanation=new_explanation,
                matched_keywords=new_score_data.get("matched_keywords", []),
                job_keywords=new_score_data.get("job_keywords", []),
                resume_word_count=len(rewrite_result["rewritten_text"].split()),
                job_description_word_count=len(request.job_description.split()),
            ),
            message="Resume enhanced successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Rewrite failed")
        raise HTTPException(status_code=500, detail=f"Resume enhancement failed: {e}")


@app.get("/download/{download_id}")
async def download_rewritten_resume(download_id: str):
    """Download a rewritten resume PDF by its unique ID."""
    # Validate format: only hex characters allowed (prevents path traversal)
    if not re.match(r"^[a-f0-9]{32}$", download_id):
        raise HTTPException(status_code=400, detail="Invalid download ID format.")

    pdf_path = DOWNLOAD_DIR / f"{download_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File not found or has expired.")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename="enhanced_resume.pdf",
        headers={"Content-Disposition": "attachment; filename=enhanced_resume.pdf"},
    )


# ── Mount frontend static assets (CSS, JS) ──────────────────────────────────
# Must be after all API routes to avoid shadowing /analyze, /health, /docs

if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


# ── Dev Server ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
