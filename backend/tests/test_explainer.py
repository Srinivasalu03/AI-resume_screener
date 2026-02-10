"""Tests for the explanation generation service."""

from app.services.explainer import generate_explanation


class TestGenerateExplanation:
    def _gen(self, score, matched=None, job_kw=None):
        return generate_explanation(
            score=score,
            matched_keywords=matched or [],
            job_keywords=job_kw,
        )

    def test_excellent_tier(self):
        text = self._gen(85, matched=["python", "docker"])
        assert "Excellent" in text
        assert "🎯" in text
        assert "python" in text

    def test_good_tier(self):
        text = self._gen(65)
        assert "Good" in text
        assert "✅" in text

    def test_moderate_tier(self):
        text = self._gen(45)
        assert "Moderate" in text
        assert "⚠️" in text

    def test_low_tier(self):
        text = self._gen(20)
        assert "Low" in text
        assert "❌" in text

    def test_includes_improvement_when_below_80(self):
        text = self._gen(
            50,
            matched=["python"],
            job_kw=["python", "docker", "aws"],
        )
        assert "Improvement" in text
        assert "docker" in text

    def test_no_improvement_when_excellent(self):
        text = self._gen(
            90,
            matched=["python", "docker"],
            job_kw=["python", "docker"],
        )
        assert "Improvement" not in text

    def test_recommendation_always_present(self):
        for score in [10, 45, 65, 90]:
            text = self._gen(score)
            assert "Recommendation" in text
