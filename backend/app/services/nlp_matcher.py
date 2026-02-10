"""
NLP Matching Service

Calculates similarity between a resume and job description using multiple
signals: TF-IDF cosine similarity, keyword overlap ratio, and skill coverage.

Scoring approach:
  - TF-IDF cosine similarity captures overall textual similarity (40% weight)
  - Keyword overlap ratio measures how many important JD terms appear in the
    resume (40% weight)
  - Length-adjusted bonus rewards detailed resumes that cover the JD breadth
    (20% weight)

These are combined into a 0-100 score that maps to recruiter-friendly tiers.
"""

import logging
import re
from collections import Counter
from typing import Dict, List

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

# ── NLTK bootstrap ───────────────────────────────────────────────────────────

for resource, path in [
    ("punkt", "tokenizers/punkt"),
    ("stopwords", "corpora/stopwords"),
]:
    try:
        nltk.data.find(path)
    except LookupError:
        logger.info("Downloading NLTK resource: %s", resource)
        nltk.download(resource, quiet=True)

STOP_WORDS = set(stopwords.words("english"))


# ── Text preprocessing ───────────────────────────────────────────────────────

def preprocess_text(text: str) -> str:
    """Remove English stopwords and return space-joined tokens."""
    tokens = word_tokenize(text.lower())
    return " ".join(w for w in tokens if w.isalnum() and w not in STOP_WORDS)


def extract_keywords(text: str, top_n: int = 15) -> List[str]:
    """
    Extract the top-N keywords from *text* using TF-IDF scores.

    Falls back to word-frequency ranking if TF-IDF fails (e.g. empty input).
    """
    processed = preprocess_text(text)
    if not processed.strip():
        return []

    try:
        vec = TfidfVectorizer(max_features=100, ngram_range=(1, 2), min_df=1)
        matrix = vec.fit_transform([processed])
        names = vec.get_feature_names_out()
        scores = matrix.toarray()[0]
        ranked = sorted(zip(names, scores), key=lambda x: x[1], reverse=True)
        return [word for word, _ in ranked[:top_n]]
    except Exception:
        counts = Counter(processed.split())
        return [w for w, _ in counts.most_common(top_n)]


# ── Main scoring function ───────────────────────────────────────────────────

def calculate_match_score(resume_text: str, job_description: str) -> Dict:
    """
    Multi-signal resume-to-JD matching.

    Returns a dict with:
      score            – combined 0-100 score
      cosine_score     – raw cosine similarity (0-1)
      matched_keywords – keywords present in both texts
      job_keywords     – important JD keywords (for the explainer)
    """
    from app.services.pdf_parser import clean_text

    resume_clean = clean_text(resume_text)
    job_clean = clean_text(job_description)

    resume_processed = preprocess_text(resume_clean)
    job_processed = preprocess_text(job_clean)

    # Guard: if either document is empty after cleaning, return zero score
    if not resume_processed.strip() or not job_processed.strip():
        return {
            "score": 0.0,
            "cosine_score": 0.0,
            "matched_keywords": [],
            "job_keywords": [],
        }

    try:
        return _score_tfidf(resume_processed, job_processed, job_description)
    except Exception as e:
        logger.warning("TF-IDF scoring failed, using fallback: %s", e)
        return _score_fallback(resume_processed, job_processed)


def _score_tfidf(
    resume_processed: str,
    job_processed: str,
    job_description_raw: str,
) -> Dict:
    """
    Primary scoring path using TF-IDF + multiple signals.

    Signal 1 – Cosine similarity (40%)
        Measures overall textual similarity between the TF-IDF vectors.

    Signal 2 – Keyword coverage (40%)
        What fraction of the top JD keywords appear in the resume?
        This directly answers: "does the candidate have the required skills?"

    Signal 3 – Breadth bonus (20%)
        Rewards resumes whose vocabulary overlaps broadly with the JD.
        Computed as |intersection| / |jd_unique_words|, capped at 1.
    """
    vectorizer = TfidfVectorizer(
        max_features=500,
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    tfidf_matrix = vectorizer.fit_transform([resume_processed, job_processed])

    # Signal 1: cosine similarity
    cosine_sim = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])

    # Find matched keywords (non-zero in both vectors)
    matched_keywords = _find_matched_keywords(vectorizer, tfidf_matrix)

    # Signal 2: keyword coverage (word-boundary match to avoid false positives)
    job_keywords = extract_keywords(job_description_raw, top_n=15)
    resume_lower = resume_processed.lower()
    if job_keywords:
        hits = sum(
            1 for kw in job_keywords
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', resume_lower)
        )
        keyword_coverage = hits / len(job_keywords)
    else:
        keyword_coverage = 0.0

    # Signal 3: breadth bonus (word-level overlap)
    resume_words = set(resume_processed.split())
    job_words = set(job_processed.split())
    if job_words:
        breadth = len(resume_words & job_words) / len(job_words)
    else:
        breadth = 0.0

    # Weighted combination → 0-100 scale
    raw = (0.40 * cosine_sim) + (0.40 * keyword_coverage) + (0.20 * min(breadth, 1.0))
    score = round(min(raw * 100, 100.0), 2)

    return {
        "score": score,
        "cosine_score": cosine_sim,
        "matched_keywords": matched_keywords,
        "job_keywords": job_keywords,
    }


def _find_matched_keywords(
    vectorizer: TfidfVectorizer, tfidf_matrix
) -> List[str]:
    """Return keywords that appear in both the resume and JD, ranked by combined TF-IDF weight."""
    names = vectorizer.get_feature_names_out()
    resume_scores = tfidf_matrix[0].toarray()[0]
    job_scores = tfidf_matrix[1].toarray()[0]

    matched = [
        (name, rs + js)
        for name, rs, js in zip(names, resume_scores, job_scores)
        if rs > 0 and js > 0
    ]
    matched.sort(key=lambda x: x[1], reverse=True)
    return [word for word, _ in matched[:15]]


def _score_fallback(resume_text: str, job_text: str) -> Dict:
    """Jaccard-based fallback when TF-IDF fails."""
    resume_words = set(resume_text.split())
    job_words = set(job_text.split())
    common = resume_words & job_words
    union = resume_words | job_words
    sim = len(common) / len(union) if union else 0.0
    return {
        "score": round(sim * 100, 2),
        "cosine_score": sim,
        "matched_keywords": sorted(common)[:15],
        "job_keywords": sorted(job_words)[:10],
    }
