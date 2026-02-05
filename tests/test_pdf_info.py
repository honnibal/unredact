"""Tests for PDF font information extraction."""

import tempfile
from pathlib import Path

import pytest

from unredact import TextSpan, extract_font_info, create_test_pdf
from unredact.widths import FontT


FONTS: list[FontT] = ["arial", "courier new", "times new roman"]


@pytest.fixture(scope="module")
def sample_pdfs() -> dict[FontT, bytes]:
    """Generate a test PDF for each font and return as bytes."""
    results: dict[FontT, bytes] = {}
    for font in FONTS:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = Path(f.name)
        create_test_pdf(["Hello World"], font, 12, pdf_path)
        results[font] = pdf_path.read_bytes()
        pdf_path.unlink()
    return results


class TestExtractFontInfo:
    """Test extract_font_info against generated PDFs."""

    @pytest.mark.parametrize("font", FONTS)
    def test_returns_spans(self, font, sample_pdfs):
        """Should return at least one TextSpan for a PDF with text."""
        spans = extract_font_info(sample_pdfs[font])
        assert len(spans) >= 1
        assert all(isinstance(s, TextSpan) for s in spans)

    @pytest.mark.parametrize("font", FONTS)
    def test_size_matches(self, font, sample_pdfs):
        """Extracted size should match the size used to create the PDF."""
        spans = extract_font_info(sample_pdfs[font])
        sizes = {s.font.size for s in spans}
        assert 12.0 in sizes

    @pytest.mark.parametrize("font", FONTS)
    def test_matched_font(self, font, sample_pdfs):
        """matched_font should map back to the correct FontT."""
        spans = extract_font_info(sample_pdfs[font])
        matched = {s.font.matched_font for s in spans}
        assert font in matched

    @pytest.mark.parametrize("font", FONTS)
    def test_bbox_is_valid(self, font, sample_pdfs):
        """Each span should have a bounding box with positive width/height."""
        spans = extract_font_info(sample_pdfs[font])
        for span in spans:
            x0, y0, x1, y1 = span.bbox
            assert x1 > x0, f"bbox width not positive: {span.bbox}"
            assert y1 > y0, f"bbox height not positive: {span.bbox}"

    @pytest.mark.parametrize("font", FONTS)
    def test_page_number(self, font, sample_pdfs):
        """Single-page PDF should have all spans on page 0."""
        spans = extract_font_info(sample_pdfs[font])
        assert all(s.page == 0 for s in spans)

    def test_empty_pdf(self):
        """An empty PDF (no text) should return an empty list."""
        import fitz

        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()

        assert extract_font_info(pdf_bytes) == []

    def test_multi_font_pdf(self):
        """A PDF with multiple fonts should return spans for each."""
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Hello", fontname="helv", fontsize=10)
        page.insert_text((50, 100), "World", fontname="cour", fontsize=14)
        pdf_bytes = doc.tobytes()
        doc.close()

        spans = extract_font_info(pdf_bytes)
        font_names = {s.font.name for s in spans}
        assert len(font_names) >= 2

    def test_real_document(self):
        """Test against the real Epstein document if available."""
        doc_path = Path(__file__).parent / "data" / "EFTA02730271.pdf"
        if not doc_path.exists():
            pytest.skip("Real document not available")

        pdf_bytes = doc_path.read_bytes()
        spans = extract_font_info(pdf_bytes)
        assert len(spans) >= 1
        for span in spans:
            assert span.font.name
            assert span.font.size > 0
            assert span.page >= 0
