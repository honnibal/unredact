"""Tests for width calculation accuracy against PDF ground truth."""

import tempfile
from pathlib import Path

import pytest

from unredact import FontCache, calculate_width, create_test_pdf, read_text_widths
from unredact.widths import FontT

# Epstein-associated names
EPSTEIN_NAMES = [
    "Jeffrey Epstein",
    "Ghislaine Maxwell",
    "Jean-Luc Brunel",
    "Sarah Kellen",
    "Nadia Marcinkova",
    "Lesley Groff",
    "Adriana Ross",
    "Alan Dershowitz",
    "Prince Andrew",
    "Bill Clinton",
    "Donald Trump",
    "Bill Gates",
    "Les Wexner",
    "Jes Staley",
    "Leon Black",
    "Glenn Dubin",
    "Eva Dubin",
    "Bill Richardson",
    "George Mitchell",
    "Marvin Minsky",
    "Stephen Hawking",
    "Lawrence Krauss",
    "Steven Pinker",
    "Reid Hoffman",
    "Woody Allen",
    "Kevin Spacey",
    "Chris Tucker",
    "Naomi Campbell",
    "Courtney Love",
    "Virginia Giuffre",
    "Maria Farmer",
    "Annie Farmer",
]

# Test strings with varying character widths
TEST_STRINGS = [
    "A",
    "AB",
    "ABC",
    "Test",
    "Hello",
    "ABCDEFGH",
    "John Smith",
    "UPPERCASE TEXT",
    "lowercase text",
    "MixedCase Text",
    "12345",
    "Numbers 123 Here",
    "Special-Chars_Test",
    "The quick brown fox",
    "MMMMMMMMMM",
    "iiiiiiiiii",
    "WWWWWWWWWW",
    "llllllllll",
    "New York, NY",
    "Palm Beach, FL",
    "Little St. James",
    "9 East 71st Street",
    "Jane Doe 1",
    "Jane Doe 2",
]

ALL_TEST_STRINGS = EPSTEIN_NAMES + TEST_STRINGS
# Note: Courier New is excluded because PyMuPDF has known issues extracting
# monospace font text (inserts spaces between characters) and reports
# incorrect bbox widths, making ground-truth comparison unreliable.
FONTS: list[FontT] = ["arial", "calibri", "cambria", "times new roman"]
SIZES = [10, 12]


@pytest.fixture(scope="module")
def font_cache():
    """Pre-loaded font cache for all fonts."""
    return FontCache(FONTS)


@pytest.fixture(scope="module")
def pdf_widths():
    """Generate PDFs and measure all string widths for each font/size combo."""
    results: dict[tuple[FontT, int], dict[str, float]] = {}

    for font in FONTS:
        for size in SIZES:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                pdf_path = Path(f.name)

            create_test_pdf(ALL_TEST_STRINGS, font, size, pdf_path)
            measurements = read_text_widths(pdf_path)
            pdf_path.unlink()

            results[(font, size)] = {text: width for text, width in measurements}

    return results


class TestWidthCalculation:
    """Test that calculate_width matches PDF-rendered widths."""

    @pytest.mark.parametrize("font", FONTS)
    @pytest.mark.parametrize("size", SIZES)
    @pytest.mark.parametrize("text", ALL_TEST_STRINGS)
    def test_width(self, text, font, size, font_cache, pdf_widths):
        """HarfBuzz width should match PDF width within 2px."""
        pdf_width = pdf_widths[(font, size)][text]
        hb_width = calculate_width(text, font, size, font_cache)

        diff = abs(pdf_width - hb_width)
        assert diff <= 2.0, (
            f"PDF={pdf_width:.1f}px, HarfBuzz={hb_width}px, diff={diff:.1f}px"
        )
