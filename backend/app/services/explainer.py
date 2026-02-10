"""
Explanation Generation Service

Produces recruiter-friendly, structured explanations of match scores.
Each explanation includes: tier header, assessment, matched skills,
improvement areas, and a hiring recommendation.
"""

from typing import List, Optional


# Score tier definitions: (min_score, label, emoji, assessment, recommendation)
_TIERS = [
    (
        80,
        "Excellent",
        "🎯",
        "This resume is a strong match for the position. The candidate demonstrates highly relevant skills and experience.",
        "Strong candidate. Recommend scheduling an interview.",
    ),
    (
        60,
        "Good",
        "✅",
        "This resume shows solid alignment with the job requirements. The candidate covers most key areas.",
        "Worth reviewing in detail. Consider for an interview.",
    ),
    (
        40,
        "Moderate",
        "⚠️",
        "This resume has some relevant experience but appears to be missing key qualifications.",
        "Consider if the missing qualifications can be learned on the job.",
    ),
    (
        0,
        "Low",
        "❌",
        "This resume shows limited alignment with the job requirements.",
        "May not be the best fit for this specific role.",
    ),
]


def _get_tier(score: float):
    """Return (label, emoji, assessment, recommendation) for the given score."""
    for min_score, label, emoji, assessment, recommendation in _TIERS:
        if score >= min_score:
            return label, emoji, assessment, recommendation
    # Fallback to lowest tier
    return _TIERS[-1][1], _TIERS[-1][2], _TIERS[-1][3], _TIERS[-1][4]


def generate_explanation(
    resume_text: str,
    job_description: str,
    score: float,
    matched_keywords: List[str],
    job_keywords: Optional[List[str]] = None,
) -> str:
    """
    Build a human-readable explanation of the match result.

    Sections:
      1. Tier header with emoji and percentage
      2. One-line assessment
      3. Matched keywords list (if any)
      4. Improvement suggestions (if score < 80 and missing keywords exist)
      5. Hiring recommendation
    """
    label, emoji, assessment, recommendation = _get_tier(score)

    parts = [
        f"{emoji} **{label} Match ({score:.1f}%)**",
        f"\n{assessment}\n",
    ]

    # Matched keywords
    if matched_keywords:
        top = matched_keywords[:10]
        parts.append("**Key Matching Skills/Keywords:**")
        parts.append(", ".join(f"'{kw}'" for kw in top))
        parts.append("")

    # Improvement areas (only when score leaves room for improvement)
    if job_keywords and score < 80:
        matched_set = {kw.lower() for kw in matched_keywords}
        missing = [kw for kw in job_keywords if kw.lower() not in matched_set]
        if missing:
            parts.append("**Areas for Improvement:**")
            parts.append(
                "The resume could be strengthened by highlighting experience with: "
                + ", ".join(f"'{kw}'" for kw in missing[:5])
            )
            parts.append("")

    parts.append(f"**Recommendation:** {recommendation}")
    return "\n".join(parts)
