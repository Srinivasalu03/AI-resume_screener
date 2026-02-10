# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Resume Screener is a web application that uses NLP (Natural Language Processing) to match resumes against job descriptions. It extracts text from PDF resumes, calculates similarity scores using TF-IDF and cosine similarity, and provides human-readable explanations with recommendations.

**Tech Stack:**
- Backend: FastAPI (Python) with scikit-learn for NLP
- Frontend: Vanilla JavaScript
- PDF Processing: PyPDF2 and pdfplumber
- Text Processing: NLTK, sentence-transformers

## Development Commands

### Backend Setup and Running

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment (first time only)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run development server (with auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Alternative: Run directly
python app/main.py
```

The backend will be available at:
- API: http://localhost:8000
- Interactive API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Frontend

The frontend is vanilla JavaScript served as static files. Simply open `frontend/index.html` in a browser or use a simple HTTP server:

```bash
cd frontend
python -m http.server 3000
```

## Architecture

### Request Flow

```
1. User uploads PDF + job description → POST /analyze
2. Validate file (PDF, max 5MB) and text (min 10 chars)
3. Save PDF temporarily to uploads/
4. Extract text from PDF (PyPDF2 fallback to pdfplumber)
5. Clean and preprocess text (lowercase, remove stopwords)
6. Calculate TF-IDF vectors for both texts
7. Compute cosine similarity (0-100 score)
8. Extract matched keywords using TF-IDF scores
9. Generate human-readable explanation with recommendations
10. Return JSON response
11. Cleanup: delete temporary PDF
```

### Core Services (backend/app/services/)

**pdf_parser.py**
- Extracts text from PDF files using dual-method approach
- Primary: PyPDF2 (faster), fallback: pdfplumber (more accurate)
- Includes `clean_text()` function: removes emails, URLs, special chars, normalizes whitespace

**nlp_matcher.py**
- Calculates similarity score using TF-IDF vectorization and cosine similarity
- `calculate_match_score()`: Main function, returns score (0-100), matched keywords, and job keywords
- `extract_keywords()`: Uses TF-IDF to extract top N important keywords
- `preprocess_text()`: Removes NLTK stopwords before analysis
- Fallback: Basic Jaccard similarity if TF-IDF fails

**explainer.py**
- Generates human-readable explanations based on score ranges:
  - 80-100: "Excellent Match" - Strong candidate
  - 60-79: "Good Match" - Review in detail
  - 40-59: "Moderate Match" - Missing key qualifications
  - 0-39: "Low Match" - Limited alignment
- Includes matched keywords and areas for improvement

### Data Models (backend/app/models/schemas.py)

Key Pydantic schemas:
- `AnalysisResponse`: Main API response with score, explanation, matched keywords, metadata
- `MatchData`: Core scoring results (score, matched_keywords, word counts)
- `FileMetadata`: File info (filename, size)
- `ErrorResponse`: Standardized error format

Helper functions:
- `create_success_response()`: Builds successful analysis response
- `create_error_response()`: Builds error response

### API Endpoints (backend/app/main.py)

- `GET /`: Welcome message with endpoint list
- `GET /health`: Health check (upload dir status, config info)
- `POST /analyze`: Main endpoint - accepts multipart/form-data with resume PDF and job_description text

## Key Patterns

### Error Handling
- Service functions raise exceptions with descriptive messages
- Main endpoint catches exceptions and converts to HTTPException with appropriate status codes
- All file operations include cleanup in try/finally blocks to prevent temp file accumulation

### File Processing
- Files temporarily saved to `backend/uploads/` directory (created on startup)
- MAX_FILE_SIZE: 5MB
- Only PDF files allowed
- Files are deleted after processing regardless of success/failure

### NLTK Data
- nltk_matcher.py auto-downloads required data (punkt tokenizer, stopwords) on first import
- Check for existing data before downloading to avoid redundant downloads

### CORS Configuration
- Currently set to `allow_origins=["*"]` for development
- In production, should be restricted to specific frontend domain

## Important Notes

- The application processes files synchronously - large PDFs may cause timeout for concurrent requests
- NLTK downloads happen once per environment on first service import
- TF-IDF uses ngram_range=(1,2) to capture both single words and 2-word phrases for better matching
- Cosine similarity of 0 means completely different texts, 1 means identical (scaled to 0-100 for user display)
