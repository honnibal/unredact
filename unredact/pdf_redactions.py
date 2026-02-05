"""Detect redaction boxes in PDF documents."""

from dataclasses import dataclass

import fitz


@dataclass(frozen=True)
class RedactionBox:
    """A detected redaction rectangle in a PDF.

    Attributes:
        page: 0-indexed page number
        bbox: Bounding box as (x0, y0, x1, y1) in PDF points
    """

    page: int
    bbox: tuple[float, float, float, float]

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]


def _find_annotation_redactions(doc: fitz.Document) -> list[RedactionBox]:
    """Find redactions marked as PDF annotations (type Redact)."""
    results: list[RedactionBox] = []
    for page_num, page in enumerate(doc):
        for annot in page.annots() or []:
            if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                r = annot.rect
                results.append(RedactionBox(
                    page=page_num,
                    bbox=(r.x0, r.y0, r.x1, r.y1),
                ))
    return results


def _find_vector_redactions(doc: fitz.Document) -> list[RedactionBox]:
    """Find filled black rectangles in the page drawing commands."""
    results: list[RedactionBox] = []
    for page_num, page in enumerate(doc):
        for drawing in page.get_drawings():
            fill = drawing.get("fill")
            if fill is None:
                continue
            # Check if fill is black or near-black
            if isinstance(fill, tuple) and all(c <= 0.1 for c in fill):
                r = drawing["rect"]
                w = r.width
                h = r.height
                if w >= 15 and h >= 5:
                    results.append(RedactionBox(
                        page=page_num,
                        bbox=(r.x0, r.y0, r.x1, r.y1),
                    ))
    return results


def _get_dark_runs(
    samples: bytes, y: int, width: int, threshold: int, min_width: int,
) -> list[tuple[int, int]]:
    """Find horizontal runs of dark pixels in a single row."""
    runs: list[tuple[int, int]] = []
    in_run = False
    start = 0
    offset = y * width
    for x in range(width):
        if samples[offset + x] < threshold:
            if not in_run:
                in_run = True
                start = x
        else:
            if in_run:
                if x - start >= min_width:
                    runs.append((start, x))
                in_run = False
    if in_run and width - start >= min_width:
        runs.append((start, width))
    return runs


def _runs_match(
    a: list[tuple[int, int]], b: list[tuple[int, int]], tolerance: int,
) -> bool:
    """Check if two sets of horizontal runs are approximately the same."""
    if len(a) != len(b) or not a:
        return False
    return all(
        abs(ra[0] - rb[0]) <= tolerance and abs(ra[1] - rb[1]) <= tolerance
        for ra, rb in zip(a, b)
    )


def _find_image_redactions(
    doc: fitz.Document,
    *,
    dpi: int = 150,
    dark_threshold: int = 80,
    min_height_pt: float = 5,
    min_width_pt: float = 15,
) -> list[RedactionBox]:
    """Find dark rectangular regions in the rendered page image.

    This handles scanned PDFs where redactions are baked into the page
    image rather than represented as annotations or vector drawings.
    """
    results: list[RedactionBox] = []
    # Minimum pixel dimensions for a dark run to be considered
    run_tolerance = 3  # pixels of wobble allowed between rows
    min_rows = 5  # minimum consecutive dark rows to form a rectangle

    for page_num, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        w, h = pix.width, pix.height
        samples = pix.samples
        scale_x = page.rect.width / w
        scale_y = page.rect.height / h
        min_run_px = int(min_width_pt / scale_x)

        prev_runs: list[tuple[int, int]] = []
        rect_start_y = 0

        for y in range(h):
            runs = _get_dark_runs(samples, y, w, dark_threshold, min_run_px)
            if _runs_match(runs, prev_runs, run_tolerance):
                continue

            # Close previous rectangles
            if prev_runs and (y - rect_start_y) >= min_rows:
                for run in prev_runs:
                    results.append(RedactionBox(
                        page=page_num,
                        bbox=(
                            run[0] * scale_x,
                            rect_start_y * scale_y,
                            run[1] * scale_x,
                            y * scale_y,
                        ),
                    ))
            prev_runs = runs
            rect_start_y = y

        # Close final rectangles
        if prev_runs and (h - rect_start_y) >= min_rows:
            for run in prev_runs:
                results.append(RedactionBox(
                    page=page_num,
                    bbox=(
                        run[0] * scale_x,
                        rect_start_y * scale_y,
                        run[1] * scale_x,
                        h * scale_y,
                    ),
                ))

    # Filter by minimum height
    results = [r for r in results if r.height >= min_height_pt]
    return results


def find_redactions(pdf_bytes: bytes) -> list[RedactionBox]:
    """Find redaction boxes in a PDF document.

    Checks three sources in order:
    1. PDF redaction annotations
    2. Filled black vector rectangles
    3. Dark rectangular regions in the rendered page image (for scans)

    Args:
        pdf_bytes: Raw bytes of the PDF file

    Returns:
        List of RedactionBox objects sorted by page, then top-to-bottom.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    results = _find_annotation_redactions(doc)
    results.extend(_find_vector_redactions(doc))
    results.extend(_find_image_redactions(doc))

    doc.close()

    results.sort(key=lambda r: (r.page, r.bbox[1], r.bbox[0]))
    return results
