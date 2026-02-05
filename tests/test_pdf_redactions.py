"""Tests for PDF redaction detection."""

from pathlib import Path

import fitz
import pytest

from unredact import RedactionBox, find_redactions


class TestFindRedactions:
    """Test find_redactions against known inputs."""

    def test_empty_pdf(self):
        """An empty PDF should return no redactions."""
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        assert find_redactions(pdf_bytes) == []

    def test_white_pdf(self):
        """A PDF with only text should return no redactions."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Hello World", fontsize=12)
        pdf_bytes = doc.tobytes()
        doc.close()
        assert find_redactions(pdf_bytes) == []

    def test_vector_black_rect(self):
        """A filled black rectangle should be detected."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Hello World", fontsize=12)
        # Draw a black filled rectangle (simulating a redaction)
        rect = fitz.Rect(100, 100, 200, 115)
        shape = page.new_shape()
        shape.draw_rect(rect)
        shape.finish(fill=(0, 0, 0))
        shape.commit()
        pdf_bytes = doc.tobytes()
        doc.close()

        boxes = find_redactions(pdf_bytes)
        assert len(boxes) >= 1
        # At least one box should overlap the drawn rectangle
        found = any(
            abs(b.bbox[0] - 100) < 5
            and abs(b.bbox[2] - 200) < 5
            and b.page == 0
            for b in boxes
        )
        assert found, f"Expected rect near (100,100)-(200,115), got {boxes}"

    def test_redaction_has_valid_dimensions(self):
        """Detected redactions should have positive width and height."""
        doc = fitz.open()
        page = doc.new_page()
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 50, 200, 65))
        shape.finish(fill=(0, 0, 0))
        shape.commit()
        pdf_bytes = doc.tobytes()
        doc.close()

        boxes = find_redactions(pdf_bytes)
        for box in boxes:
            assert box.width > 0
            assert box.height > 0

    def test_sorted_by_page_and_position(self):
        """Results should be sorted by page, then y, then x."""
        doc = fitz.open()
        for _ in range(2):
            page = doc.new_page()
            shape = page.new_shape()
            # Two rects on each page
            shape.draw_rect(fitz.Rect(50, 200, 150, 215))
            shape.finish(fill=(0, 0, 0))
            shape.draw_rect(fitz.Rect(50, 100, 150, 115))
            shape.finish(fill=(0, 0, 0))
            shape.commit()
        pdf_bytes = doc.tobytes()
        doc.close()

        boxes = find_redactions(pdf_bytes)
        for i in range(1, len(boxes)):
            prev, curr = boxes[i - 1], boxes[i]
            assert (prev.page, prev.bbox[1]) <= (curr.page, curr.bbox[1])

    def test_real_document(self):
        """Test against the real Epstein document if available."""
        doc_path = Path(__file__).parent / "data" / "EFTA02730271.pdf"
        if not doc_path.exists():
            pytest.skip("Real document not available")

        pdf_bytes = doc_path.read_bytes()
        boxes = find_redactions(pdf_bytes)
        # Document is known to contain redactions
        assert len(boxes) > 10
        for box in boxes:
            assert box.width >= 15
            assert box.height >= 5
            assert box.page >= 0
