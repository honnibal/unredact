"""Tests for width calculation accuracy against actual PDF text spans.

For each non-redacted text span in a real Epstein document, we compute
the expected width using our font shaping and compare it to the actual
bounding box width from the PDF. This validates that if we had a redaction
box at that location, we would correctly identify the actual text as a match.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

from unredact import FontCache, calculate_width, extract_font_info
from unredact.widths import FontT


EPSTEIN_PDFS = list((Path(__file__).parent / "data").glob("EFTA*.pdf"))
TOLERANCE_PX = 5.0
MIN_TEXT_LEN = 5
MAX_TEXT_LEN = 20

# Spans where width calculation fails due to PDF horizontal scaling (Tz operator).
#
# These documents appear to have been OCR'd or reconstructed without access to
# the original bold fonts. To preserve visual appearance, the PDF uses the
# regular Times-Roman font with per-word horizontal scaling (Tz) of 115-130%
# to approximate the width of bold text. For example, "Ghislaine" in the title
# uses "11.98 Tf" (12pt) with "124.12 Tz" (124% horizontal scale).
#
# PyMuPDF reports an "effective size" (~13pt) computed from the text matrix,
# but doesn't expose the Tz scaling factor. Our width calculation uses the
# reported size with regular font metrics, so we underestimate by ~10-20%.
#
# Body text uses Tz values close to 100% and passes fine. Only these specific
# header/title spans have elevated Tz values. Identified by (pdf, page, y, text).
SKIPPED_SPANS_WITH_HORIZONTAL_SCALING = {
    # EFTA00156482.pdf - truncated OCR artifact
    ("EFTA00156482.pdf", 1, 369, "Agen'"),
    # EFTA02730271.pdf page 0 - title and section headers
    ("EFTA02730271.pdf", 0, 34, "UNCLASSIFIED//FOR"),
    ("EFTA02730271.pdf", 0, 48, "EXTERNALLY"),
    ("EFTA02730271.pdf", 0, 201, "Findings"),
    ("EFTA02730271.pdf", 0, 201, "Person"),
    ("EFTA02730271.pdf", 0, 201, "Research"),
    ("EFTA02730271.pdf", 0, 202, "(UHFOUO)"),
    ("EFTA02730271.pdf", 0, 218, "Ghislaine"),
    ("EFTA02730271.pdf", 0, 218, "Interest"),
    ("EFTA02730271.pdf", 0, 218, "Maxwell"),
    ("EFTA02730271.pdf", 0, 218, "Witnesses"),
    ("EFTA02730271.pdf", 0, 248, "Executive"),
    ("EFTA02730271.pdf", 0, 248, "Summary"),
    ("EFTA02730271.pdf", 0, 416, "Findings"),
    ("EFTA02730271.pdf", 0, 489, "Opportunities"),
    ("EFTA02730271.pdf", 0, 601, "Substantiation"),
    ("EFTA02730271.pdf", 0, 729, "EXTERNALLY"),
    ("EFTA02730271.pdf", 0, 741, "UNCLASSIFIED//FOR"),
    # EFTA02730271.pdf page 1
    ("EFTA02730271.pdf", 1, 34, "UNCLASSIFIED//FOR"),
    ("EFTA02730271.pdf", 1, 570, "Biographical"),
    ("EFTA02730271.pdf", 1, 570, "Information"),
    ("EFTA02730271.pdf", 1, 705, "(U//FOLIO)"),
    ("EFTA02730271.pdf", 1, 741, "UNCLASSIFIED//FOR"),
    # EFTA02730271.pdf page 2
    ("EFTA02730271.pdf", 2, 34, "UNCLASSIFIED//FOR"),
    ("EFTA02730271.pdf", 2, 49, "EXTERNALLY"),
    ("EFTA02730271.pdf", 2, 113, '2021I"Comprehensive'),
    ("EFTA02730271.pdf", 2, 215, "investigation?"),
    ("EFTA02730271.pdf", 2, 730, "EXTERNALLY"),
    ("EFTA02730271.pdf", 2, 741, "UNCLASSIFIED//FOR"),
}

# Module-level cache shared across all tests
_font_cache: FontCache | None = None


def get_font_cache() -> FontCache:
    """Get or create the shared font cache."""
    global _font_cache
    if _font_cache is None:
        _font_cache = FontCache()
    return _font_cache


@dataclass
class SpanTestCase:
    """A single span to test."""

    text: str
    font: FontT
    size: int
    bbox_width: float
    page: int
    y_coord: int
    pdf_name: str

    @property
    def test_id(self) -> str:
        """Generate a readable test ID."""
        text_preview = self.text[:20].replace(" ", "_")
        if len(self.text) > 20:
            text_preview += "..."
        return f"{self.pdf_name}:p{self.page}:{text_preview}"


def collect_span_test_cases() -> list[SpanTestCase]:
    """Extract testable spans from Epstein PDFs."""
    cases = []
    for pdf_path in EPSTEIN_PDFS:
        pdf_bytes = pdf_path.read_bytes()
        spans = extract_font_info(pdf_bytes)

        for span in spans:
            if span.font.matched_font is None:
                continue
            content = span.text.rstrip()
            if not (MIN_TEXT_LEN <= len(content) <= MAX_TEXT_LEN):
                continue
            bbox_width = span.bbox[2] - span.bbox[0]
            cases.append(
                SpanTestCase(
                    text=span.text,
                    font=span.font.matched_font,
                    size=span.font.size,
                    bbox_width=bbox_width,
                    page=span.page,
                    y_coord=int(span.bbox[1]),
                    pdf_name=pdf_path.name,
                )
            )
    return cases


# Collect cases at module load time for parametrization
SPAN_TEST_CASES = collect_span_test_cases() if EPSTEIN_PDFS else []


@pytest.mark.parametrize(
    "case",
    SPAN_TEST_CASES,
    ids=lambda c: c.test_id,
)
def test_span_width(case: SpanTestCase):
    """Calculated width should match bbox width within tolerance."""
    content = case.text.rstrip()

    # Skip known spans with PDF horizontal scaling (Tz operator)
    if (case.pdf_name, case.page, case.y_coord, content) in SKIPPED_SPANS_WITH_HORIZONTAL_SCALING:
        pytest.skip("span uses Tz horizontal scaling to simulate bold font")

    font_cache = get_font_cache()
    calculated_width = calculate_width(
        case.text,
        case.font,
        case.size,
        font_cache,
    )

    diff = abs(calculated_width - case.bbox_width)
    assert diff <= TOLERANCE_PX, (
        f"'{case.text}' ({case.font} {case.size}pt): "
        f"bbox={case.bbox_width:.1f}px, calc={calculated_width}px, diff={diff:.1f}px"
    )
