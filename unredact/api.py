"""FastAPI web service for text width calculation."""

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from .cache import fetch_pdf, validate_url
from .pdf_info import FontInfo, TextSpan, extract_font_info
from .pdf_redactions import find_redactions
from .settings import Settings
from .widths import FONT_FILES, FontCache, FontT, calculate_width

_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Global state, initialized on startup
font_cache: FontCache | None = None
settings: Settings | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load fonts and settings on startup."""
    global font_cache, settings
    font_cache = FontCache(list(FONT_FILES.keys()))
    settings = Settings()
    yield


app = FastAPI(
    title="Text Width Calculator",
    description="Calculate pixel widths of text strings for redaction matching",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
def index():
    """Serve the frontend."""
    return FileResponse(_STATIC_DIR / "index.html")


class WidthRequest(BaseModel):
    """Request to calculate text widths.

    Strings are automatically stripped of leading/trailing whitespace.
    Width calculations for strings with trailing spaces are unreliable
    due to variable word-spacing in PDFs.
    """

    strings: list[str]
    font: FontT = "times new roman"
    size: int = 12
    kerning: bool = True
    ligatures: bool = True

    @field_validator("strings")
    @classmethod
    def strip_whitespace(cls, v: list[str]) -> list[str]:
        """Strip leading/trailing whitespace from all strings."""
        return [s.strip() for s in v]


class WidthResult(BaseModel):
    """Width calculation for a single string."""

    text: str
    width: int


class WidthResponse(BaseModel):
    """Response with calculated widths."""

    font: str
    size: int
    kerning: bool
    ligatures: bool
    results: list[WidthResult]


@app.post("/widths", response_model=WidthResponse)
def calculate_widths(request: WidthRequest) -> WidthResponse:
    """Calculate pixel widths for a list of strings."""
    if font_cache is None:
        raise HTTPException(status_code=503, detail="Font cache not initialized")

    results = [
        WidthResult(
            text=s,
            width=calculate_width(
                s,
                request.font,
                request.size,
                font_cache,
                kerning=request.kerning,
                ligatures=request.ligatures,
            ),
        )
        for s in request.strings
    ]

    return WidthResponse(
        font=request.font,
        size=request.size,
        kerning=request.kerning,
        ligatures=request.ligatures,
        results=results,
    )


@app.get("/fonts")
def list_fonts() -> list[str]:
    """List available fonts."""
    return list(FONT_FILES.keys())


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    if font_cache is None:
        raise HTTPException(status_code=503, detail="Font cache not initialized")
    return {"status": "ok"}


# --- PDF analysis by URL ---


class FontInfoResult(BaseModel):
    """Font properties for a single text span."""

    name: str
    size: int
    bold: bool
    italic: bool
    matched_font: str | None


class TextSpanResult(BaseModel):
    """A text span with its font and location."""

    text: str
    font: FontInfoResult
    page: int
    bbox: tuple[float, float, float, float]


class FontAnalysisResponse(BaseModel):
    """Response from the font analysis endpoint."""

    url: str
    spans: list[TextSpanResult]


class UrlRequest(BaseModel):
    """Request containing a PDF URL."""

    url: str


@app.post("/fonts/by-url", response_model=FontAnalysisResponse)
def analyse_fonts_by_url(request: UrlRequest) -> FontAnalysisResponse:
    """Extract font information from a PDF at the given URL.

    The URL must be from an allowed domain (e.g. justice.gov).
    """
    if settings is None:
        raise HTTPException(status_code=503, detail="Settings not initialized")

    try:
        validate_url(request.url, allowed_domains=settings.allowed_domains)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        pdf_bytes = fetch_pdf(request.url, settings)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch PDF: {e.response.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch PDF: {e}")

    spans = extract_font_info(pdf_bytes)

    return FontAnalysisResponse(
        url=request.url,
        spans=[
            TextSpanResult(
                text=s.text,
                font=FontInfoResult(
                    name=s.font.name,
                    size=s.font.size,
                    bold=s.font.bold,
                    italic=s.font.italic,
                    matched_font=s.font.matched_font,
                ),
                page=s.page,
                bbox=s.bbox,
            )
            for s in spans
        ],
    )


class RedactionBoxResult(BaseModel):
    """A detected redaction rectangle."""

    page: int
    bbox: tuple[float, float, float, float]
    width: float
    height: float


class RedactionsResponse(BaseModel):
    """Response from the redactions endpoint."""

    url: str
    redactions: list[RedactionBoxResult]


@app.post("/redactions/by-url", response_model=RedactionsResponse)
def find_redactions_by_url(request: UrlRequest) -> RedactionsResponse:
    """Find redaction boxes in a PDF at the given URL.

    The URL must be from an allowed domain (e.g. justice.gov).
    """
    if settings is None:
        raise HTTPException(status_code=503, detail="Settings not initialized")

    try:
        validate_url(request.url, allowed_domains=settings.allowed_domains)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        pdf_bytes = fetch_pdf(request.url, settings)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch PDF: {e.response.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch PDF: {e}")

    boxes = find_redactions(pdf_bytes)

    return RedactionsResponse(
        url=request.url,
        redactions=[
            RedactionBoxResult(
                page=b.page,
                bbox=b.bbox,
                width=b.width,
                height=b.height,
            )
            for b in boxes
        ],
    )
