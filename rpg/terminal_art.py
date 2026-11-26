"""Terminal-safe art assets and optional local image conversion."""

from dataclasses import dataclass
from pathlib import Path


ART_STYLES = {
    "classic": ("Classic ASCII", "Ten levels of shading using ordinary punctuation and letters."),
    "shaded": ("Fine Shaded ASCII", "A longer character ramp for smooth gradients and detailed faces."),
    "line": ("ASCII Line Art", "Sparse outlines that leave room for dialogue and scenery."),
    "ink": ("High Contrast ASCII", "Three strong tones for clear silhouettes in small portraits."),
    "blocks": ("Unicode Shades", "Monochrome shading with block characters."),
    "braille": ("Braille Dots", "Eight small dots per cell render fine monochrome detail."),
    "ansi256": ("ANSI 256 Half Blocks", "Two samples per cell mapped to the xterm color palette."),
    "truecolor": ("True Color Half Blocks", "Two full RGB samples per cell for scenes and portraits."),
    "color": ("Color Blocks", "Unicode blocks with colors sampled from the picture."),
    "green": ("Green Phosphor", "Monochrome green blocks with soft shadows."),
    "amber": ("Amber Phosphor", "Monochrome amber blocks with warm highlights."),
}


@dataclass(frozen=True)
class TerminalArt:
    alt: str
    ascii_rows: tuple[str, ...]
    palette: tuple[str, ...] = ()
    color_rows: tuple[str, ...] = ()
    glyph_rows: tuple[str, ...] = ()
    color_space: str | None = None
    foreground: tuple[tuple[str | int, ...], ...] = ()
    background: tuple[tuple[str | int, ...], ...] = ()

    @classmethod
    def from_data(cls, data: dict) -> "TerminalArt":
        rows = tuple(data["ascii"])
        palette = tuple(data.get("palette", []))
        colors = tuple(data.get("colors", []))
        alt = data["alt"]
        if not isinstance(alt, str) or not alt.isprintable():
            raise ValueError("Terminal art needs printable alt text.")
        if (not rows or len(rows) > 24 or not 1 <= len(rows[0]) <= 56
                or any(not isinstance(row, str) or len(row) != len(rows[0])
                       or not row.isascii() or not row.isprintable() for row in rows)):
            raise ValueError("Terminal art must be a printable ASCII rectangle up to 56 by 24.")
        if colors or palette:
            if (not 1 <= len(palette) <= 16 or len(colors) != len(rows)
                    or any(len(color) != 6 or any(char not in "0123456789abcdef" for char in color)
                           for color in palette)
                    or any(len(row) != len(rows[0]) or any(char not in "0123456789abcdef"[:len(palette)]
                                                         for char in row) for row in colors)):
                raise ValueError("Invalid terminal art color grid.")
        glyphs = tuple(data.get("glyphs", []))
        if glyphs and (len(glyphs) != len(rows) or any(
            not isinstance(row, str) or len(row) != len(rows[0]) or any(
                glyph not in " ░▒▓█▀▄" and not 0x2800 <= ord(glyph) <= 0x28FF for glyph in row
            ) for row in glyphs
        )):
            raise ValueError("Invalid terminal art glyph grid.")
        space = data.get("color_space")
        foreground = tuple(tuple(row) for row in data.get("foreground", []))
        background = tuple(tuple(row) for row in data.get("background", []))
        if space or foreground or background:
            if (space not in {"xterm256", "rgb"} or not glyphs or palette or any(
                len(grid) != len(rows) or any(
                    len(row) != len(rows[0]) or any(not valid_color(cell, space) for cell in row)
                    for row in grid
                ) for grid in (foreground, background)
            )):
                raise ValueError("Invalid per-cell terminal art colors.")
        return cls(alt, rows, palette, colors, glyphs, space, foreground, background)

    def as_data(self) -> dict:
        data = {"alt": self.alt, "ascii": list(self.ascii_rows)}
        if self.palette:
            data.update(palette=list(self.palette), colors=list(self.color_rows))
        if self.glyph_rows:
            data["glyphs"] = list(self.glyph_rows)
        if self.color_space:
            data.update(color_space=self.color_space, foreground=[list(row) for row in self.foreground],
                        background=[list(row) for row in self.background])
        return data


def valid_color(value: str | int, space: str) -> bool:
    if space == "xterm256":
        return type(value) is int and 0 <= value < 256
    return isinstance(value, str) and len(value) == 6 and all(char in "0123456789abcdef" for char in value)


def shaded_rows(luminance: bytes, width: int, levels: str, bias: int = 0) -> list[str]:
    return [
        "".join(levels[(value * (len(levels) - 1) + bias) // 255] for value in luminance[index:index + width])
        for index in range(0, len(luminance), width)
    ]


def line_rows(luminance: bytes, width: int, height: int) -> list[str]:
    rows = []
    for y in range(height):
        line = []
        for x in range(width):
            dx = luminance[y * width + min(x + 1, width - 1)] - luminance[y * width + max(x - 1, 0)]
            dy = luminance[min(y + 1, height - 1) * width + x] - luminance[max(y - 1, 0) * width + x]
            if abs(dx) + abs(dy) < 44:
                glyph = " "
            elif abs(dx) > abs(dy) * 1.7:
                glyph = "|"
            elif abs(dy) > abs(dx) * 1.7:
                glyph = "-"
            else:
                glyph = "/" if dx * dy > 0 else chr(92)
            line.append(glyph)
        rows.append("".join(line))
    return rows


def braille_rows(luminance: bytes, width: int, height: int) -> list[str]:
    # The two columns occupy separate ranges of Unicode dot bits except on the fourth row.
    offsets = ((0, 0, 0, 40), (0, 1, 1, 160), (0, 2, 2, 80), (0, 3, 6, 200),
               (1, 0, 3, 144), (1, 1, 4, 56), (1, 2, 5, 216), (1, 3, 7, 104))
    return [
        "".join(chr(0x2800 + sum(
            1 << bit for dx, dy, bit, threshold in offsets
            if luminance[(y * 4 + dy) * width * 2 + x * 2 + dx] >= threshold
        )) for x in range(width))
        for y in range(height)
    ]


def xterm_color(pixel: tuple[int, int, int]) -> int:
    levels = (0, 95, 135, 175, 215, 255)
    indices = [min(range(6), key=lambda index: abs(value - levels[index])) for value in pixel]
    cube_error = sum((value - levels[index]) ** 2 for value, index in zip(pixel, indices))
    gray_index = max(0, min(23, round((sum(pixel) / 3 - 8) / 10)))
    gray = 8 + 10 * gray_index
    if sum((value - gray) ** 2 for value in pixel) < cube_error:
        return 232 + gray_index
    return 16 + 36 * indices[0] + 6 * indices[1] + indices[2]


def half_block_colors(upper_lower, width: int, height: int, style: str) -> dict:
    pixels = list(upper_lower.get_flattened_data()) if hasattr(upper_lower, "get_flattened_data") else list(upper_lower.getdata())
    if style == "ansi256":
        colors = [xterm_color(pixel) for pixel in pixels]
    else:
        colors = ["%02x%02x%02x" % pixel for pixel in pixels]
    rows = [colors[index:index + width] for index in range(0, len(colors), width)]
    return {
        "glyphs": ["▀" * width] * height,
        "color_space": "xterm256" if style == "ansi256" else "rgb",
        "foreground": rows[::2], "background": rows[1::2],
    }


def convert_image(source: Path, *, alt: str, width: int = 24, height: int = 10,
                  mode: str = "ascii", crop: list[int] | None = None,
                  contrast: float = 1.15, style: str | None = None) -> TerminalArt:
    try:
        from PIL import Image, ImageEnhance, ImageOps
    except ImportError as error:
        raise ValueError("Image conversion requires Pillow. Install requirements-authoring.txt.") from error
    if not 4 <= width <= 56 or not 2 <= height <= 24:
        raise ValueError("Art size must be 4–56 columns by 2–24 rows.")
    if mode not in {"ascii", "color"} or not 0.25 <= contrast <= 3:
        raise ValueError("Use ascii or color mode and a contrast between 0.25 and 3.")
    style = style if style is not None else ("color" if mode == "color" else "classic")
    if style not in ART_STYLES:
        raise ValueError(f"Unknown art style {style!r}. Choose from {', '.join(ART_STYLES)}.")
    with Image.open(source) as source_image:
        image = ImageOps.exif_transpose(source_image).convert("RGBA")
        if crop is not None:
            if (len(crop) != 4 or not all(isinstance(value, int) for value in crop)
                    or not (0 <= crop[0] < crop[2] <= image.width and 0 <= crop[1] < crop[3] <= image.height)):
                raise ValueError("Crop must be [left, top, right, bottom] inside the image.")
            image = image.crop(tuple(crop))
        backdrop = Image.new("RGBA", image.size, "#111813")
        backdrop.alpha_composite(image)
        # Fit to the physical canvas before compressing two vertical pixels into each cell.
        size = (width * 2, height * 4) if style == "braille" else (width, height * 2)
        fitted = ImageOps.fit(backdrop.convert("RGB"), size, Image.Resampling.LANCZOS)
        pixels = ImageEnhance.Contrast(fitted.resize((width, height), Image.Resampling.LANCZOS)).enhance(contrast)
    grayscale = pixels.convert("L")
    if style == "ink":
        grayscale = ImageOps.autocontrast(grayscale, cutoff=2)
    levels = {"ink": " +@", "shaded": " .,'`^:\";Il!i><~+_-?][}{1)(|/*tfjrxnuvczXYUJCLQ0OZmwqpdbkhao#MW&8%B@$"}
    luminance = grayscale.tobytes()
    rows = shaded_rows(luminance, width, levels.get(style, " .:-=+*#%@"), 127 if style == "ink" else 0)
    data = {"alt": alt, "ascii": rows}
    if style == "line":
        data["ascii"] = line_rows(luminance, width, height)
    elif style == "blocks":
        data["glyphs"] = shaded_rows(luminance, width, " ░▒▓█", 127)
    elif style == "braille":
        dots = ImageEnhance.Contrast(fitted.convert("L")).enhance(contrast)
        data["glyphs"] = braille_rows(dots.tobytes(), width, height)
    elif style in {"ansi256", "truecolor"}:
        data.update(half_block_colors(ImageEnhance.Contrast(fitted).enhance(contrast), width, height, style))
    if style in {"color", "green", "amber"}:
        if style in {"green", "amber"}:
            black, highlight = ("#07140d", "#98ffb0") if style == "green" else ("#190f06", "#ffc66b")
            pixels = ImageOps.colorize(grayscale, black, highlight)
        indexed = pixels.quantize(colors=16)
        indices = indexed.tobytes()
        raw = indexed.getpalette()
        data["palette"] = ["".join(f"{part:02x}" for part in raw[index:index + 3])
                           for index in range(0, (max(indices) + 1) * 3, 3)]
        data["colors"] = ["".join(f"{value:x}" for value in indices[index:index + width])
                          for index in range(0, len(indices), width)]
    return TerminalArt.from_data(data)
