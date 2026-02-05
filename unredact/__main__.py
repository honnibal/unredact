"""CLI for analyzing PDF files.

Usage:
    python -m unredact <file.pdf> [file2.pdf ...]
    python -m unredact --summary <file.pdf>
    python -m unredact --redactions <file.pdf>
"""

import argparse
import sys
from pathlib import Path

from .pdf_info import extract_font_info, FontInfo
from .pdf_redactions import find_redactions


def _format_color(color: int) -> str:
    """Format an integer color as #RRGGBB."""
    return f"#{color:06x}"


def _print_spans(path: Path, pdf_bytes: bytes) -> None:
    spans = extract_font_info(pdf_bytes)
    if not spans:
        print(f"{path}: no text found")
        return

    print(f"{path}: {len(spans)} spans\n")
    for span in spans:
        f = span.font
        match = f.matched_font or "?"
        style = ""
        if f.bold:
            style += "B"
        if f.italic:
            style += "I"
        x0, y0, x1, y1 = span.bbox
        print(
            f"  p{span.page} ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})  "
            f"{f.name} {f.size}pt{style}  [{match}]  "
            f"{_format_color(f.color)}  {span.text!r}"
        )


def _print_summary(path: Path, pdf_bytes: bytes) -> None:
    spans = extract_font_info(pdf_bytes)
    if not spans:
        print(f"{path}: no text found")
        return

    # Count spans per unique FontInfo
    counts: dict[FontInfo, int] = {}
    for span in spans:
        counts[span.font] = counts.get(span.font, 0) + 1

    print(f"{path}: {len(spans)} spans, {len(counts)} unique fonts\n")
    print(f"  {'Font':<30} {'Size':>5} {'Style':<5} {'Match':<18} {'Color':<9} {'Spans':>5}")
    print(f"  {'-'*30} {'-'*5} {'-'*5} {'-'*18} {'-'*9} {'-'*5}")

    for font, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].name)):
        style = ""
        if font.bold:
            style += "B"
        if font.italic:
            style += "I"
        match = font.matched_font or "?"
        print(
            f"  {font.name:<30} {font.size:>5.1f} {style:<5} {match:<18} "
            f"{_format_color(font.color):<9} {count:>5}"
        )


def _print_redactions(path: Path, pdf_bytes: bytes) -> None:
    boxes = find_redactions(pdf_bytes)
    if not boxes:
        print(f"{path}: no redactions found")
        return

    print(f"{path}: {len(boxes)} redactions\n")
    for box in boxes:
        x0, y0, x1, y1 = box.bbox
        print(
            f"  p{box.page} ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})  "
            f"{box.width:.0f}x{box.height:.0f}pt"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze PDF files for fonts and redactions.",
    )
    parser.add_argument("files", nargs="+", type=Path, help="PDF files to analyze")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--summary", "-s", action="store_true",
        help="Show unique font summary",
    )
    mode.add_argument(
        "--redactions", "-r", action="store_true",
        help="Find redaction boxes",
    )
    args = parser.parse_args()

    for path in args.files:
        if not path.exists():
            print(f"Error: {path} not found", file=sys.stderr)
            sys.exit(1)
        pdf_bytes = path.read_bytes()
        if args.summary:
            _print_summary(path, pdf_bytes)
        elif args.redactions:
            _print_redactions(path, pdf_bytes)
        else:
            _print_spans(path, pdf_bytes)
        if len(args.files) > 1:
            print()


main()
