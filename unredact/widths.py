import platform
from pathlib import Path
from typing import Literal

import uharfbuzz as hb

FontT = Literal[
    "arial",
    "calibri",
    "cambria",
    "courier new",
    "helvetica",
    "times new roman",
]

# Map font names to possible file names (without path)
# Uses open-source metric-compatible substitutes when originals unavailable:
# - Liberation Sans / Arimo: substitute for Arial
# - Carlito: substitute for Calibri
# - Caladea: substitute for Cambria
# - Liberation Mono / Cousine: substitute for Courier New
# - Helvetica falls back to Arial / Liberation Sans when unavailable
# - Liberation Serif / Tinos: substitute for Times New Roman
FONT_FILES: dict[FontT, list[str]] = {
    "arial": ["Arial.ttf", "LiberationSans-Regular.ttf", "Arimo-Regular.ttf"],
    "calibri": ["Calibri.ttf", "Carlito-Regular.ttf"],
    "cambria": ["Cambria.ttf", "Caladea-Regular.ttf"],
    "courier new": ["Courier New.ttf", "cour.ttf", "LiberationMono-Regular.ttf", "Cousine-Regular.ttf"],
    "helvetica": ["Helvetica.ttc", "Helvetica.ttf", "Arial.ttf", "LiberationSans-Regular.ttf", "Arimo-Regular.ttf"],
    "times new roman": ["Times New Roman.ttf", "times.ttf", "LiberationSerif-Regular.ttf", "Tinos-Regular.ttf"],
}


def _get_font_path(font: FontT) -> Path:
    """Get the system font path for a given font name."""
    filenames = FONT_FILES[font]
    system = platform.system()

    if system == "Darwin":
        search_paths = [
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library/Fonts",
        ]
    elif system == "Windows":
        search_paths = [Path(r"C:\Windows\Fonts")]
    else:  # Linux
        search_paths = [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
        ]

    for filename in filenames:
        for base in search_paths:
            candidate = base / filename
            if candidate.exists():
                return candidate
            for match in base.rglob(filename):
                return match

    raise FileNotFoundError(f"Font file not found: {filenames}")


class FontCache:
    """Pre-loads and caches HarfBuzz font objects."""

    def __init__(self, fonts: list[FontT] | None = None):
        """Load specified fonts, or all known fonts if none specified."""
        self.faces: dict[FontT, hb.Face] = {}
        self.upem: dict[FontT, int] = {}

        to_load = fonts if fonts is not None else list(FONT_FILES.keys())
        for font_name in to_load:
            path = _get_font_path(font_name)
            blob = hb.Blob.from_file_path(str(path))
            face = hb.Face(blob)
            self.faces[font_name] = face
            self.upem[font_name] = face.upem


def calculate_width(
    string: str,
    font: FontT,
    size: int,
    cache: FontCache,
    *,
    kerning: bool = True,
    ligatures: bool = True,
) -> int:
    """Calculate the rendered width in pixels.

    Args:
        string: The text to measure
        font: Font name (must be pre-loaded in cache)
        size: Font size in points
        cache: Pre-loaded font cache
        kerning: Whether to apply kerning (default True)
        ligatures: Whether to apply standard ligatures (default True)

    Returns:
        Width in pixels (at 72 DPI, where 1pt = 1px)
    """
    face = cache.faces[font]
    upem = cache.upem[font]

    hb_font = hb.Font(face)
    hb_font.scale = (upem, upem)

    buf = hb.Buffer()
    buf.add_str(string)
    buf.guess_segment_properties()

    features: dict[str, bool] = {}
    if not kerning:
        features["kern"] = False
    if not ligatures:
        features["liga"] = False

    hb.shape(hb_font, buf, features)

    positions = buf.glyph_positions
    total_advance = sum(pos.x_advance for pos in positions)

    width_px = total_advance * size / upem

    return int(round(width_px))
