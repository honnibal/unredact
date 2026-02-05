"""Generate test PDFs and read back text widths for validation."""

from pathlib import Path

import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .widths import FontT, _get_font_path


def create_test_pdf(
    strings: list[str],
    font: FontT,
    size: float,
    output_path: Path,
) -> None:
    """Create a PDF with each string on its own line.

    Args:
        strings: List of strings to render
        font: Font name to use
        size: Font size in points
        output_path: Where to save the PDF
    """
    # Register the font with reportlab
    font_path = _get_font_path(font)
    font_name = f"Test-{font.replace(' ', '')}"
    pdfmetrics.registerFont(TTFont(font_name, str(font_path)))

    # Create PDF
    c = canvas.Canvas(str(output_path), pagesize=letter)
    _, page_height = letter

    # Start from top of page with margin
    y_position = page_height - 50
    x_position = 50
    line_height = size * 1.5

    c.setFont(font_name, size)

    for string in strings:
        if y_position < 50:
            # Start new page if we run out of space
            c.showPage()
            c.setFont(font_name, size)
            y_position = page_height - 50

        c.drawString(x_position, y_position, string)
        y_position -= line_height

    c.save()


def read_text_widths(pdf_path: Path) -> list[tuple[str, float]]:
    """Read text strings and their widths from a PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        List of (text, width_in_pixels) tuples for each text span found
    """
    doc = fitz.open(str(pdf_path))
    results: list[tuple[str, float]] = []

    for page in doc:
        # Get text with detailed position info
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        for block in blocks:
            if block["type"] != 0:  # Skip non-text blocks
                continue

            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"]
                    bbox = span["bbox"]  # (x0, y0, x1, y1)
                    width = bbox[2] - bbox[0]

                    if text.strip():  # Skip empty spans
                        results.append((text, width))

    doc.close()
    return results


def create_and_measure(
    strings: list[str],
    font: FontT,
    size: float,
    output_path: Path | None = None,
) -> dict[str, float]:
    """Create a test PDF and measure the rendered widths.

    Args:
        strings: List of strings to test
        font: Font name to use
        size: Font size in points
        output_path: Where to save the PDF (uses temp file if None)

    Returns:
        Dict mapping each string to its measured pixel width
    """
    import tempfile

    if output_path is None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            output_path = Path(f.name)

    create_test_pdf(strings, font, size, output_path)
    measurements = read_text_widths(output_path)

    # Build dict from measurements
    result: dict[str, float] = {}
    for text, width in measurements:
        result[text] = width

    return result
