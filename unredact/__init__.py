"""Unredaction tools for matching redaction boxes to names."""

from .widths import FontT, FontCache, calculate_width
from .pdf_test_data import create_test_pdf, read_text_widths, create_and_measure
from .pdf_info import FontInfo, TextSpan, extract_font_info
from .pdf_redactions import RedactionBox, find_redactions
from .settings import Settings
from .cache import CacheResult, validate_url, check_cache, ensure_in_cache

__all__ = [
    "FontT",
    "FontCache",
    "calculate_width",
    "create_test_pdf",
    "read_text_widths",
    "create_and_measure",
    "FontInfo",
    "TextSpan",
    "extract_font_info",
    "RedactionBox",
    "find_redactions",
    "Settings",
    "CacheResult",
    "validate_url",
    "check_cache",
    "ensure_in_cache",
]
