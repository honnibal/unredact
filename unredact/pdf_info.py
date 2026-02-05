"""Extract font information from PDF documents."""

from dataclasses import dataclass

import fitz

from .widths import FontT


# Map substrings in PDF font names to our supported FontT values.
# Ordered so more-specific substrings are checked before less-specific ones
# (e.g. "liberation sans" before "liberation" to avoid mismatches).
_FONT_NAME_MAP: list[tuple[str, FontT]] = [
    ("liberation sans", "arial"),
    ("liberation mono", "courier new"),
    ("liberation serif", "times new roman"),
    ("arial", "arial"),
    ("arimo", "arial"),
    ("helvetica", "helvetica"),
    ("calibri", "calibri"),
    ("carlito", "calibri"),
    ("cambria", "cambria"),
    ("caladea", "cambria"),
    ("courier", "courier new"),
    ("cousine", "courier new"),
    ("times", "times new roman"),
    ("tinos", "times new roman"),
]


@dataclass(frozen=True)
class FontInfo:
    """Font properties extracted from a PDF span.

    Attributes:
        name: Raw PDF font name (e.g. "TimesNewRomanPSMT")
        size: Font size in points (rounded to nearest integer)
        bold: Whether the font is bold
        italic: Whether the font is italic
        monospaced: Whether the font is monospaced
        serif: Whether the font is a serif font
        color: Text color as an integer
        matched_font: Corresponding FontT value, or None if unrecognized
    """

    name: str
    size: int
    bold: bool
    italic: bool
    monospaced: bool
    serif: bool
    color: int
    matched_font: FontT | None


@dataclass(frozen=True)
class TextSpan:
    """A span of text with its font properties and location in the PDF.

    Attributes:
        text: The text content of the span
        font: Font properties for this span
        page: 0-indexed page number
        bbox: Bounding box as (x0, y0, x1, y1) in PDF points
    """

    text: str
    font: FontInfo
    page: int
    bbox: tuple[float, float, float, float]


def _match_font(pdf_font_name: str) -> FontT | None:
    """Match a PDF font name to a supported FontT value."""
    lower = pdf_font_name.lower()
    for substring, font_t in _FONT_NAME_MAP:
        if substring in lower:
            return font_t
    return None


def extract_font_info(pdf_bytes: bytes) -> list[TextSpan]:
    """Extract text spans with font information from a PDF.

    Each span represents a contiguous run of text with the same font
    properties. Spans preserve their page number and bounding box so
    that font information can be associated with specific regions of
    the document.

    Args:
        pdf_bytes: Raw bytes of the PDF file

    Returns:
        List of TextSpan objects in document order (page, then top-to-bottom,
        left-to-right).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    spans: list[TextSpan] = []

    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        for block in blocks:
            if block["type"] != 0:  # Skip non-text blocks
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if not span["text"].strip():
                        continue
                    flags = span["flags"]
                    font = FontInfo(
                        name=span["font"],
                        size=round(span["size"]),
                        bold=bool(flags & 16),
                        italic=bool(flags & 2),
                        monospaced=bool(flags & 8),
                        serif=bool(flags & 4),
                        color=span["color"],
                        matched_font=_match_font(span["font"]),
                    )
                    bbox = span["bbox"]
                    spans.append(TextSpan(
                        text=span["text"],
                        font=font,
                        page=page_num,
                        bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
                    ))

    doc.close()
    return spans
