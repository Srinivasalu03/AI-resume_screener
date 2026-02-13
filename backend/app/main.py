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
    ATSCheckItem,
    ATSCheckRequest,
    ATSCheckResponse,
    CoverLetterRequest,
    CoverLetterResponse,
    HealthCheckResponse,
    MatchData,
    RecommendationsRequest,
    RecommendationsResponse,
    ResumeProfile,
    JobRecommendation,
    RewriteRequest,
    RewriteResponse,
    create_success_response,
)
from app.services.pdf_parser import extract_text_from_pdf
from app.services.nlp_matcher import calculate_match_score
from app.services.explainer import generate_explanation
from app.services.resume_rewriter import rewrite_resume
from app.services.pdf_generator import generate_resume_pdf
from app.services.job_recommender import generate_recommendations
from app.services.section_scorer import calculate_section_scores
from app.services.cover_letter_generator import generate_cover_letter, generate_cover_letter_pdf
from app.services.ats_checker import check_ats_compatibility
from app.services.format_preserver import extract_layout, generate_format_preserved_pdf, LayoutMetadata

logger = logging.getLogger(__name__)

# ── Layout Cache (in-memory, keyed by layout_id) ────────────────────────────
# Stores extracted layout metadata so the /rewrite endpoint can use it.
# Entries expire after LAYOUT_CACHE_TTL seconds.
_layout_cache: dict[str, tuple[LayoutMetadata, float]] = {}
LAYOUT_CACHE_TTL = 3600  # 1 hour


def _cache_layout(layout: LayoutMetadata) -> str:
    """Store layout in cache and return its ID."""
    layout_id = uuid.uuid4().hex
    _layout_cache[layout_id] = (layout, time.time())
    # Evict expired entries
    cutoff = time.time() - LAYOUT_CACHE_TTL
    expired = [k for k, (_, ts) in _layout_cache.items() if ts < cutoff]
    for k in expired:
        _layout_cache.pop(k, None)
    return layout_id


def _get_cached_layout(layout_id: str) -> LayoutMetadata | None:
    """Retrieve layout from cache if still valid."""
    entry = _layout_cache.get(layout_id)
    if entry is None:
        return None
    layout, ts = entry
    if time.time() - ts > LAYOUT_CACHE_TTL:
        _layout_cache.pop(layout_id, None)
        return None
    return layout

# ── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Resume Screener API",
    description="Match resumes to job descriptions using NLP (TF-IDF + cosine similarity)",
    version="5.0.0",
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
        "endpoints": {"analyze": "/analyze", "health": "/health", "rewrite": "/rewrite", "recommendations": "/recommendations", "cover-letter": "/cover-letter", "ats-check": "/ats-check"},
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

        # Step 1b: Extract layout metadata for format-preserving enhancement
        layout = extract_layout(file_path)
        layout_id = _cache_layout(layout)

        # Step 2: Calculate match score via NLP
        score_data = calculate_match_score(resume_text, job_description)

        # Step 3: Generate human-readable explanation
        explanation = generate_explanation(
            score=score_data["score"],
            matched_keywords=score_data.get("matched_keywords", []),
            job_keywords=score_data.get("job_keywords", []),
        )

        # Step 4: Calculate per-section confidence scores
        section_scores_data = calculate_section_scores(
            resume_text=resume_text,
            job_description=job_description,
            job_keywords=score_data.get("job_keywords", []),
        )

        # Step 5: Build and return response
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
            section_scores=section_scores_data,
            layout_id=layout_id,
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
            role_preference=request.role_preference,
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

        # Step 3: Generate downloadable PDF (format-preserving if layout available)
        download_id = uuid.uuid4().hex
        pdf_path = DOWNLOAD_DIR / f"{download_id}.pdf"

        formatting_preserved = False
        formatting_notes: list[str] = []

        cached_layout = _get_cached_layout(request.layout_id) if request.layout_id else None

        if cached_layout and cached_layout.formatting_preserved:
            # Use format-preserving generation
            _, formatting_notes = generate_format_preserved_pdf(
                resume_text=rewrite_result["rewritten_text"],
                sections=rewrite_result.get("sections", {}),
                layout=cached_layout,
                output_path=pdf_path,
            )
            formatting_preserved = True
            logger.info("Generated format-preserved PDF for download %s", download_id)
        else:
            # Fallback to standard generation
            generate_resume_pdf(
                resume_text=rewrite_result["rewritten_text"],
                sections=rewrite_result.get("sections", {}),
                output_path=pdf_path,
            )
            formatting_notes.append("Original formatting not available; used standard layout")

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
            formatting_preserved=formatting_preserved,
            formatting_notes=formatting_notes,
            message="Resume enhanced successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Rewrite failed")
        raise HTTPException(status_code=500, detail=f"Resume enhancement failed: {e}")


@app.post("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(request: RecommendationsRequest):
    """Generate job recommendations based on resume profile."""
    try:
        result = generate_recommendations(
            resume_text=request.resume_text,
            matched_keywords=request.matched_keywords,
            job_keywords=request.job_keywords,
        )

        return RecommendationsResponse(
            success=True,
            profile=ResumeProfile(**result["profile"]),
            recommendations=[JobRecommendation(**r) for r in result["recommendations"]],
            total_matched=result["total_matched"],
            message=f"Found {result['total_matched']} matching roles",
        )

    except Exception as e:
        logger.exception("Recommendations failed")
        raise HTTPException(status_code=500, detail=f"Recommendation generation failed: {e}")


@app.post("/cover-letter", response_model=CoverLetterResponse)
async def generate_cover_letter_endpoint(request: CoverLetterRequest):
    """Generate a tailored cover letter from resume and job description."""
    try:
        result = generate_cover_letter(
            resume_text=request.resume_text,
            job_description=request.job_description,
            matched_keywords=request.matched_keywords,
            job_keywords=request.job_keywords,
            candidate_name=request.candidate_name,
        )

        # Generate downloadable PDF
        download_id = uuid.uuid4().hex
        pdf_path = DOWNLOAD_DIR / f"cl_{download_id}.pdf"
        generate_cover_letter_pdf(
            cover_letter_text=result["cover_letter"],
            output_path=pdf_path,
        )

        return CoverLetterResponse(
            success=True,
            cover_letter=result["cover_letter"],
            word_count=result["word_count"],
            key_highlights=result["key_highlights"],
            candidate_name=result["candidate_name"],
            download_id=download_id,
            message="Cover letter generated successfully",
        )

    except Exception as e:
        logger.exception("Cover letter generation failed")
        raise HTTPException(status_code=500, detail=f"Cover letter generation failed: {e}")


@app.post("/ats-check", response_model=ATSCheckResponse)
async def ats_check_endpoint(request: ATSCheckRequest):
    """Run ATS compatibility checks on resume text."""
    try:
        result = check_ats_compatibility(
            resume_text=request.resume_text,
            filename=request.filename,
        )

        return ATSCheckResponse(
            success=True,
            score=result["score"],
            checks=[ATSCheckItem(**c) for c in result["checks"]],
            summary=result["summary"],
            pass_count=result["pass_count"],
            warning_count=result["warning_count"],
            fail_count=result["fail_count"],
            message=f"ATS compatibility score: {result['score']:.0f}/100",
        )

    except Exception as e:
        logger.exception("ATS check failed")
        raise HTTPException(status_code=500, detail=f"ATS check failed: {e}")


@app.get("/download/{download_id}")
async def download_rewritten_resume(download_id: str):
    """Download a rewritten resume PDF by its unique ID."""
    # Validate format: only hex characters allowed, optionally with cl_ prefix
    if not re.match(r"^(?:cl_)?[a-f0-9]{32}$", download_id):
        raise HTTPException(status_code=400, detail="Invalid download ID format.")

    pdf_path = DOWNLOAD_DIR / f"{download_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File not found or has expired.")

    # Determine filename based on type
    is_cover_letter = download_id.startswith("cl_")
    dl_filename = "cover_letter.pdf" if is_cover_letter else "enhanced_resume.pdf"

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=dl_filename,
        headers={"Content-Disposition": f"attachment; filename={dl_filename}"},
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
