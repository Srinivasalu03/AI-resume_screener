"""
Pydantic v2 schemas for the AI Resume Screener API.

Defines request/response models and helper constructors.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Request Schemas ──────────────────────────────────────────────────────────

class JobDescriptionRequest(BaseModel):
    """Validated job description input."""

    job_description: str = Field(
        ...,
        min_length=10,
        max_length=10_000,
        description="Job description text to match against the resume",
        examples=["We are looking for a Senior Python Developer with 5+ years of experience in FastAPI, Docker, and AWS."],
    )

    @field_validator("job_description")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Job description cannot be empty or whitespace only")
        if len(v.split()) < 5:
            raise ValueError("Job description must have at least 5 words")
        return v


# ── Response Schemas ─────────────────────────────────────────────────────────

class MatchData(BaseModel):
    """Core match analysis results."""

    score: float = Field(..., ge=0.0, le=100.0, description="Match score (0-100)")
    match_percentage: str = Field(..., description="Score formatted as percentage")
    explanation: str = Field(..., description="Human-readable match explanation")
    matched_keywords: List[str] = Field(default=[], description="Keywords in both documents")
    resume_word_count: int = Field(..., ge=0, description="Resume word count")
    job_description_word_count: int = Field(..., ge=0, description="JD word count")


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


# ── Helper Constructors ──────────────────────────────────────────────────────

def create_error_response(
    error_message: str,
    error_code: Optional[str] = None,
    details: Optional[dict] = None,
) -> ErrorResponse:
    """Build a standardized error response."""
    return ErrorResponse(success=False, error=error_message, error_code=error_code, details=details)


def create_success_response(
    score: float,
    explanation: str,
    matched_keywords: List[str],
    resume_word_count: int,
    job_word_count: int,
    filename: str,
    file_size_kb: float,
) -> AnalysisResponse:
    """Build a standardized success response."""
    return AnalysisResponse(
        success=True,
        data=MatchData(
            score=round(score, 2),
            match_percentage=f"{round(score, 1)}%",
            explanation=explanation,
            matched_keywords=matched_keywords,
            resume_word_count=resume_word_count,
            job_description_word_count=job_word_count,
        ),
        metadata=FileMetadata(
            filename=filename,
            file_size_kb=round(file_size_kb, 2),
        ),
        message="Analysis completed successfully",
    )
