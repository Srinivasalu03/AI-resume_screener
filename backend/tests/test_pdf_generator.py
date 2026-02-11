"""
Unit tests for the PDF generation service.
"""

import pytest
from pathlib import Path
from app.services.pdf_generator import generate_resume_pdf


class TestPdfGeneration:
    def test_generates_valid_pdf(self, tmp_path):
        """Generated file should be a valid PDF (starts with %PDF)."""
        output = tmp_path / "test_resume.pdf"
        generate_resume_pdf(
            resume_text="John Doe\nSoftware Developer\nExperienced in Python and JavaScript.",
            output_path=output,
        )
        assert output.exists()
        with open(output, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_generates_pdf_with_sections(self, tmp_path):
        """PDF generated with sections dict should be valid."""
        output = tmp_path / "test_structured.pdf"
        sections = {
            "header": "John Doe\njohn@email.com",
            "summary": "Summary\nExperienced software developer.",
            "skills": "Skills\nPython, JavaScript, Docker",
            "experience": "Experience\n- Built REST APIs\n- Managed databases",
            "education": "Education\nB.S. Computer Science",
        }
        generate_resume_pdf(
            resume_text="",
            sections=sections,
            output_path=output,
        )
        assert output.exists()
        assert output.stat().st_size > 0

    def test_handles_long_text(self, tmp_path):
        """Multi-page resume text should generate a valid PDF."""
        output = tmp_path / "test_long.pdf"
        long_text = "Professional Experience\n" + "\n".join(
            [f"- Completed project {i} with excellent results using advanced methodologies" for i in range(100)]
        )
        generate_resume_pdf(resume_text=long_text, output_path=output)
        assert output.exists()
        assert output.stat().st_size > 1000  # Should be reasonably large

    def test_handles_special_characters(self, tmp_path):
        """PDF should handle unicode and special characters gracefully."""
        output = tmp_path / "test_unicode.pdf"
        text = "John Doe\u2019s Resume\nExperience with C++ and C#\nWorked at Comp\u00e9tence Inc."
        generate_resume_pdf(resume_text=text, output_path=output)
        assert output.exists()

    def test_requires_output_path(self):
        """Should raise ValueError if no output path is provided."""
        with pytest.raises(ValueError, match="output_path"):
            generate_resume_pdf(resume_text="test", output_path=None)

    def test_empty_text_generates_pdf(self, tmp_path):
        """Even empty text should produce a valid (albeit blank) PDF."""
        output = tmp_path / "test_empty.pdf"
        generate_resume_pdf(resume_text="", output_path=output)
        assert output.exists()
