#!/usr/bin/env python3
import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ExifTags


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
}


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def find_default_font_path() -> Optional[str]:
    """Attempt to find a reasonable default TrueType font across platforms."""
    candidate_paths = [
        # macOS common fonts
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        # Linux common fonts
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # Windows common fonts
        os.path.expandvars(r"%WINDIR%/Fonts/arial.ttf"),
    ]
    for candidate in candidate_paths:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def parse_color(color_str: str) -> Tuple[int, int, int, int]:
    """Parse color input. Accepts hex (#RRGGBB or #RRGGBBAA) or PIL color names."""
    color_str = color_str.strip()
    if color_str.startswith("#"):
        hex_str = color_str[1:]
        if len(hex_str) == 6:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return (r, g, b, 255)
        if len(hex_str) == 8:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            a = int(hex_str[6:8], 16)
            return (r, g, b, a)
        raise ValueError("Hex color must be #RRGGBB or #RRGGBBAA")
    # Fallback to PIL to parse named colors by drawing a 1x1 image
    img = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(img)
    try:
        draw.rectangle((0, 0, 1, 1), fill=color_str)
        return img.getpixel((0, 0))
    except Exception as exc:
        raise ValueError(f"Invalid color: {color_str}") from exc


def extract_exif_date(image: Image.Image) -> Optional[str]:
    """Extract date from EXIF as YYYY-MM-DD if available."""
    try:
        exif = image.getexif()
    except Exception:
        exif = None
    if not exif:
        return None

    tag_map = {ExifTags.TAGS.get(tag, tag): tag for tag in exif.keys()}

    for key in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
        if key in tag_map:
            value = exif.get(tag_map[key])
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", errors="ignore")
                except Exception:
                    value = None
            if isinstance(value, str) and len(value) >= 10:
                # Typical EXIF format: YYYY:MM:DD HH:MM:SS
                date_part = value.split()[0]
                if ":" in date_part:
                    y, m, d = date_part.split(":", 2)
                    return f"{y}-{m}-{d}"
                # Already in YYYY-MM-DD
                return date_part[:10]
    return None


@dataclass
class WatermarkOptions:
    font_size: int
    color: Tuple[int, int, int, int]
    position: str
    margin_px: int
    font_path: Optional[str]


def compute_position(
    image_size: Tuple[int, int],
    text_size: Tuple[int, int],
    position: str,
    margin: int,
) -> Tuple[int, int]:
    img_w, img_h = image_size
    text_w, text_h = text_size
    x = y = 0

    pos = position.lower()
    if pos == "top-left":
        x, y = margin, margin
    elif pos == "top-center":
        x, y = (img_w - text_w) // 2, margin
    elif pos == "top-right":
        x, y = img_w - text_w - margin, margin
    elif pos == "center-left":
        x, y = margin, (img_h - text_h) // 2
    elif pos in ("center", "middle", "centre"):
        x, y = (img_w - text_w) // 2, (img_h - text_h) // 2
    elif pos == "center-right":
        x, y = img_w - text_w - margin, (img_h - text_h) // 2
    elif pos == "bottom-left":
        x, y = margin, img_h - text_h - margin
    elif pos == "bottom-center":
        x, y = (img_w - text_w) // 2, img_h - text_h - margin
    elif pos == "bottom-right":
        x, y = img_w - text_w - margin, img_h - text_h - margin
    else:
        # default
        x, y = img_w - text_w - margin, img_h - text_h - margin

    return max(0, x), max(0, y)


def draw_watermark(image: Image.Image, text: str, options: WatermarkOptions) -> Image.Image:
    # Load font
    font: ImageFont.ImageFont
    if options.font_path:
        try:
            font = ImageFont.truetype(options.font_path, options.font_size)
        except Exception:
            font = ImageFont.load_default()
    else:
        default_font_path = find_default_font_path()
        if default_font_path:
            font = ImageFont.truetype(default_font_path, options.font_size)
        else:
            font = ImageFont.load_default()

    # Convert to RGBA to support alpha drawing
    if image.mode != "RGBA":
        base = image.convert("RGBA")
    else:
        base = image.copy()

    draw = ImageDraw.Draw(base)

    # Measure text
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x, y = compute_position(base.size, (text_w, text_h), options.position, options.margin_px)

    # Optional shadow for readability
    shadow_offset = max(1, options.font_size // 24)
    shadow_color = (0, 0, 0, min(160, options.color[3]))
    for dx, dy in ((shadow_offset, shadow_offset), (shadow_offset, 0), (0, shadow_offset)):
        draw.text((x + dx, y + dy), text, font=font, fill=shadow_color)

    # Draw main text
    draw.text((x, y), text, font=font, fill=options.color)

    return base


def process_image_file(path: Path, output_dir: Path, options: WatermarkOptions) -> Optional[Path]:
    try:
        with Image.open(path) as img:
            date_text = extract_exif_date(img)
            if not date_text:
                print(f"[skip] No EXIF date for: {path}")
                return None

            result_img = draw_watermark(img, date_text, options)

            # Preserve original format where possible
            format_hint = img.format if img.format else None

            output_name = path.stem + "_watermark" + path.suffix
            output_path = output_dir / output_name

            save_params = {}

            # Decide JPEG by output extension or source format
            output_ext = output_path.suffix.lower()
            is_jpeg_output = output_ext in {".jpeg", ".jpg"}
            is_jpeg_source = (img.format or "").lower() == "jpeg"

            if is_jpeg_output or is_jpeg_source:
                # Ensure compatible mode and format for JPEG
                if result_img.mode != "RGB":
                    result_img = result_img.convert("RGB")
                save_params["format"] = "JPEG"
                save_params.setdefault("quality", 95)
            elif format_hint:
                # For non-JPEG, keep original format if available
                save_params["format"] = format_hint

            result_img.save(output_path, **save_params)
            print(f"[ok] {path.name} -> {output_path}")
            return output_path
    except Exception as exc:
        print(f"[error] Failed to process {path}: {exc}")
        return None


def resolve_processing_dir(input_path: Path) -> Path:
    if input_path.is_dir():
        return input_path
    if input_path.is_file():
        return input_path.parent
    raise FileNotFoundError(f"Path not found: {input_path}")


def build_output_dir(source_dir: Path) -> Path:
    parent = source_dir
    name = source_dir.name + "_watermark"
    output_dir = parent / name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def gather_images(source_dir: Path) -> list[Path]:
    return [p for p in sorted(source_dir.iterdir()) if is_image_file(p)]


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add EXIF date watermark (YYYY-MM-DD) to images in the given file's directory or in the given directory."
        )
    )
    parser.add_argument(
        "path",
        type=str,
        help="Image file path or a directory path. If file, process all images in its directory.",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=36,
        help="Font size for watermark text (default: 36)",
    )
    parser.add_argument(
        "--color",
        type=str,
        default="#FFFFFFCC",
        help="Text color. Accepts hex (#RRGGBB[AA]) or named color (default: #FFFFFFCC)",
    )
    parser.add_argument(
        "--position",
        type=str,
        default="bottom-right",
        choices=[
            "top-left",
            "top-center",
            "top-right",
            "center-left",
            "center",
            "center-right",
            "bottom-left",
            "bottom-center",
            "bottom-right",
        ],
        help="Watermark position (default: bottom-right)",
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=24,
        help="Margin (pixels) from edges (default: 24)",
    )
    parser.add_argument(
        "--font",
        type=str,
        default=None,
        help="Path to a .ttf/.otf font file. If omitted, tries to auto-detect.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.path).expanduser().resolve()

    try:
        source_dir = resolve_processing_dir(input_path)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    output_dir = build_output_dir(source_dir)

    color = parse_color(args.color)
    options = WatermarkOptions(
        font_size=args.font_size,
        color=color,
        position=args.position,
        margin_px=args.margin,
        font_path=args.font,
    )

    images = gather_images(source_dir)
    if not images:
        print(f"No images found in: {source_dir}")
        return 0

    processed = 0
    for img_path in images:
        if process_image_file(img_path, output_dir, options):
            processed += 1

    print(f"Done. Processed {processed}/{len(images)} images. Output: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

