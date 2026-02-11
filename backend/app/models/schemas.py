"""
Pydantic v2 schemas for the AI Resume Screener API.

Defines request/response models and helper constructors.
"""

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Response Schemas ─────────────────────────────────────────────────────────

class MatchData(BaseModel):
    """Core match analysis results."""

    score: float = Field(..., ge=0.0, le=100.0, description="Match score (0-100)")
    match_percentage: str = Field(..., description="Score formatted as percentage")
    explanation: str = Field(..., description="Human-readable match explanation")
    matched_keywords: List[str] = Field(default=[], description="Keywords in both documents")
    job_keywords: List[str] = Field(default=[], description="Important JD keywords")
    resume_word_count: int = Field(..., ge=0, description="Resume word count")
    job_description_word_count: int = Field(..., ge=0, description="JD word count")
    resume_text: Optional[str] = Field(default=None, description="Extracted resume text (for rewrite)")


class FileMetadata(BaseModel):
    """Uploaded file metadata."""

    filename: str = Field(..., description="Original filename")
    file_size_kb: float = Field(..., ge=0, description="File size in KB")
    upload_timestamp: Optional[datetime] = Field(default=None, description="Upload time (ISO 8601)")


class AnalysisResponse(BaseModel):
    """Successful /analyze response."""

    success: bool = Field(..., description="Whether analysis completed")
    data: MatchData = Field(..., description="Analysis results")
    metadata: FileMetadata = Field(..., description="File information")
    message: Optional[str] = Field(default=None, description="Status message")


class ErrorResponse(BaseModel):
    """Error response."""

    success: bool = Field(default=False, description="Always false for errors")
    error: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(default=None, description="Machine-readable error code")
    details: Optional[dict] = Field(default=None, description="Additional error context")


class HealthCheckResponse(BaseModel):
    """Health endpoint response."""

    status: str = Field(..., description="Health status")
    upload_dir_exists: bool = Field(..., description="Upload directory accessible")
    max_file_size_mb: float = Field(..., description="Max file size (MB)")
    timestamp: Optional[datetime] = Field(default=None, description="Server time")


# ── Rewrite Schemas ──────────────────────────────────────────────────────────

class RewriteRequest(BaseModel):
    """Request body for POST /rewrite."""

    resume_text: str = Field(..., min_length=50, description="Extracted resume text")
    job_description: str = Field(..., min_length=10, description="Job description text")
    matched_keywords: List[str] = Field(default=[], description="Keywords matched in original analysis")
    job_keywords: List[str] = Field(default=[], description="Important JD keywords from original analysis")
    original_score: float = Field(..., ge=0.0, le=100.0, description="Original match score")


class RewriteResponse(BaseModel):
    """Response from POST /rewrite."""

    success: bool = Field(..., description="Whether rewrite completed")
    original_score: float = Field(..., ge=0.0, le=100.0, description="Original match score")
    updated_score: float = Field(..., ge=0.0, le=100.0, description="New match score after rewrite")
    score_improvement: float = Field(..., description="Score change (can be negative)")
    improvements_summary: List[str] = Field(default=[], description="List of changes made")
    rewritten_resume_preview: str = Field(..., description="Preview of rewritten resume")
    download_id: str = Field(..., description="UUID for PDF download")
    updated_analysis: MatchData = Field(..., description="Full re-analysis of rewritten resume")
    message: Optional[str] = Field(default=None, description="Status message")


# ── Helper Constructors ──────────────────────────────────────────────────────

def create_success_response(
    score: float,
    explanation: str,
    matched_keywords: List[str],
    resume_word_count: int,
    job_word_count: int,
    filename: str,
    file_size_kb: float,
    resume_text: Optional[str] = None,
    job_keywords: Optional[List[str]] = None,
) -> AnalysisResponse:
    """Build a standardized success response."""
    return AnalysisResponse(
        success=True,
        data=MatchData(
            score=round(score, 2),
            match_percentage=f"{round(score, 1)}%",
            explanation=explanation,
            matched_keywords=matched_keywords,
            job_keywords=job_keywords or [],
            resume_word_count=resume_word_count,
            job_description_word_count=job_word_count,
            resume_text=resume_text,
        ),
        metadata=FileMetadata(
            filename=filename,
            file_size_kb=round(file_size_kb, 2),
            upload_timestamp=datetime.now(timezone.utc),
        ),
        message="Analysis completed successfully",
    )
