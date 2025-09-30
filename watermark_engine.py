import math
import os
from typing import Tuple, Optional, Dict, Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


# Utility: clamp
def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# Utility: convert degrees to radians
def deg2rad(deg: float) -> float:
    return deg * math.pi / 180.0


# Position presets (nine-grid)
PRESET_POSITIONS = {
    "top_left": (0.0, 0.0),
    "top_center": (0.5, 0.0),
    "top_right": (1.0, 0.0),
    "center_left": (0.0, 0.5),
    "center": (0.5, 0.5),
    "center_right": (1.0, 0.5),
    "bottom_left": (0.0, 1.0),
    "bottom_center": (0.5, 1.0),
    "bottom_right": (1.0, 1.0),
}


def load_font(font_family: Optional[str], size: int, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    """
    Load a font by family name. Try to find bold/italic variants when requested.
    """
    # Ensure reasonable font size limits
    size = max(8, min(size, 500))  # Limit font size between 8 and 500
    
    print(f"Loading font: family={font_family}, size={size}, bold={bold}, italic={italic}")
    
    # Comprehensive font search for macOS
    font_search_paths = []
    
    if font_family:
        # Common font families and their actual file names on macOS
        font_files = {
            "Arial": [
                ("/System/Library/Fonts/Supplemental/Arial.ttf", False, False),
                ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", True, False),
                ("/System/Library/Fonts/Supplemental/Arial Italic.ttf", False, True),
                ("/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf", True, True),
            ],
            "Helvetica": [
                ("/System/Library/Fonts/Helvetica.ttc", False, False),
                ("/System/Library/Fonts/Helvetica.ttc", True, False),  # Same file, different index
                ("/System/Library/Fonts/Helvetica.ttc", False, True),
                ("/System/Library/Fonts/Helvetica.ttc", True, True),
            ],
            "Times": [
                ("/System/Library/Fonts/Times.ttc", False, False),
                ("/System/Library/Fonts/Times.ttc", True, False),
                ("/System/Library/Fonts/Times.ttc", False, True),
                ("/System/Library/Fonts/Times.ttc", True, True),
            ],
            "Times New Roman": [
                ("/System/Library/Fonts/Times.ttc", False, False),
                ("/System/Library/Fonts/Times.ttc", True, False),
                ("/System/Library/Fonts/Times.ttc", False, True),
                ("/System/Library/Fonts/Times.ttc", True, True),
            ]
        }
        
        if font_family in font_files:
            # Find the best matching variant with font index for .ttc files
            for font_path, is_bold, is_italic in font_files[font_family]:
                if bold == is_bold and italic == is_italic:
                    if font_path.endswith('.ttc'):
                        # For .ttc files, we need to specify the font index
                        if font_family == "Helvetica":
                            if bold and italic:
                                font_search_paths.append((font_path, 3))  # Bold Italic
                            elif bold:
                                font_search_paths.append((font_path, 1))  # Bold
                            elif italic:
                                font_search_paths.append((font_path, 2))  # Italic
                            else:
                                font_search_paths.append((font_path, 0))  # Regular
                        elif font_family in ["Times", "Times New Roman"]:
                            if bold and italic:
                                font_search_paths.append((font_path, 3))  # Bold Italic
                            elif bold:
                                font_search_paths.append((font_path, 1))  # Bold
                            elif italic:
                                font_search_paths.append((font_path, 2))  # Italic
                            else:
                                font_search_paths.append((font_path, 0))  # Regular
                        else:
                            font_search_paths.append((font_path, 0))
                    else:
                        font_search_paths.append((font_path, None))
                    break
            # If exact match not found, try regular variant
            if not font_search_paths:
                for font_path, _, _ in font_files[font_family]:
                    if font_path.endswith('.ttc'):
                        font_search_paths.append((font_path, 0))  # Regular
                    else:
                        font_search_paths.append((font_path, None))
                    break
    
    # Add fallback fonts
    font_search_paths.extend([
        ("/System/Library/Fonts/Helvetica.ttc", 0),
        ("/System/Library/Fonts/Times.ttc", 0),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", None),
    ])
    
    # Try each font path
    for font_info in font_search_paths:
        if isinstance(font_info, tuple):
            font_path, font_index = font_info
        else:
            font_path, font_index = font_info, None
            
        try:
            if os.path.exists(font_path):
                print(f"Trying font: {font_path} (index: {font_index})")
                if font_index is not None:
                    font = ImageFont.truetype(font_path, size=size, index=font_index)
                else:
                    font = ImageFont.truetype(font_path, size=size)
                print(f"Successfully loaded font: {font_path} (index: {font_index})")
                return font
        except Exception as e:
            print(f"Failed to load {font_path} (index: {font_index}): {e}")
            continue
    
    # Final fallback - try common system fonts
    fallback_fonts = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Times.ttc"
    ]
    
    for font_file in fallback_fonts:
        try:
            if os.path.exists(font_file):
                print(f"Using fallback font: {font_file}")
                return ImageFont.truetype(font_file, size=size)
        except Exception:
            continue
    
    # Last resort - default font
    print("Using default font")
    try:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def apply_resize(img: Image.Image, resize_opts: Dict[str, Any]) -> Image.Image:
    """
    Resize by width/height or percent. Keeps aspect ratio when one dimension provided.
    resize_opts: {"width": Optional[int], "height": Optional[int], "percent": Optional[float]}
    """
    width = resize_opts.get("width")
    height = resize_opts.get("height")
    percent = resize_opts.get("percent")
    if percent:
        percent = max(0.01, float(percent))
        new_size = (max(1, int(img.width * percent)), max(1, int(img.height * percent)))
        return img.resize(new_size, Image.Resampling.LANCZOS)
    if width and height:
        return img.resize((int(width), int(height)), Image.Resampling.LANCZOS)
    if width and not height:
        w = int(width)
        h = max(1, int(img.height * (w / img.width)))
        return img.resize((w, h), Image.Resampling.LANCZOS)
    if height and not width:
        h = int(height)
        w = max(1, int(img.width * (h / img.height)))
        return img.resize((w, h), Image.Resampling.LANCZOS)
    return img


def compose_text_watermark(
    text: str,
    font_family: Optional[str],
    font_size: int,
    color_rgba: Tuple[int, int, int, int],
    stroke_width: int = 0,
    stroke_rgba: Optional[Tuple[int, int, int, int]] = None,
    shadow_offset: Tuple[int, int] = (0, 0),
    shadow_rgba: Optional[Tuple[int, int, int, int]] = None,
    bold: bool = False,
    italic: bool = False,
) -> Image.Image:
    """
    Create a RGBA image containing the rendered text with optional stroke and shadow.
    """
    # Ensure valid parameters
    if not text or not text.strip():
        text = "Sample"
    
    font_size = max(8, min(font_size, 500))  # Reasonable size limits
    stroke_width = max(0, min(stroke_width, 20))  # Reasonable stroke limits
    
    print(f"Creating text watermark: '{text}' with font size {font_size}")
    
    font = load_font(font_family, size=font_size, bold=bold, italic=italic)
    
    # Preliminary size calculation
    dummy_img = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))  # Larger dummy canvas
    draw = ImageDraw.Draw(dummy_img)
    
    try:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])
    except Exception as e:
        print(f"Error calculating text size: {e}")
        # Fallback size calculation
        text_w = len(text) * font_size // 2
        text_h = font_size
    
    # Calculate padding
    shadow_pad = max(abs(shadow_offset[0]), abs(shadow_offset[1])) if shadow_offset != (0, 0) else 0
    pad = max(10, stroke_width + shadow_pad + 5)  # Extra padding for safety
    
    # Create canvas with reasonable size limits
    canvas_w = min(max(text_w + pad * 2, 50), 2000)  # Between 50 and 2000 pixels
    canvas_h = min(max(text_h + pad * 2, 20), 1000)  # Between 20 and 1000 pixels
    
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Center the text in the canvas
    x = (canvas_w - text_w) // 2
    y = (canvas_h - text_h) // 2

    # Shadow
    if shadow_rgba and (shadow_offset != (0, 0)) and len(shadow_rgba) >= 3:
        sx = x + shadow_offset[0]
        sy = y + shadow_offset[1]
        # Ensure shadow_rgba is a valid tuple
        safe_shadow_rgba = tuple(int(c) for c in shadow_rgba[:4])
        draw.text(
            (sx, sy),
            text,
            font=font,
            fill=safe_shadow_rgba,
            stroke_width=stroke_width,
            stroke_fill=safe_shadow_rgba if stroke_rgba is None else tuple(int(c) for c in stroke_rgba[:4]),
        )

    # Stroke + Text
    # Ensure color_rgba is a valid tuple
    safe_color_rgba = tuple(int(c) for c in color_rgba[:4]) if color_rgba and len(color_rgba) >= 3 else (255, 255, 255, 255)
    
    if stroke_width > 0 and stroke_rgba and len(stroke_rgba) >= 3:
        safe_stroke_rgba = tuple(int(c) for c in stroke_rgba[:4])
        draw.text((x, y), text, font=font, fill=safe_color_rgba, stroke_width=stroke_width, stroke_fill=safe_stroke_rgba)
    else:
        draw.text((x, y), text, font=font, fill=safe_color_rgba)

    return canvas


def compose_image_watermark(
    wm_img: Image.Image,
    scale: float,
    opacity: float,
) -> Image.Image:
    """
    Prepare image watermark with scale and opacity. wm_img should be RGBA.
    """
    scale = max(0.01, scale)
    new_size = (max(1, int(wm_img.width * scale)), max(1, int(wm_img.height * scale)))
    wm = wm_img.resize(new_size, Image.Resampling.LANCZOS)
    if opacity < 1.0:
        alpha = wm.split()[-1]
        alpha = ImageEnhanceBrightness(alpha).enhance(opacity)  # custom helper below
        wm.putalpha(alpha)
    return wm


class ImageEnhanceBrightness:
    """
    Minimal enhancer for alpha to emulate opacity scaling: output = alpha * opacity
    """
    def __init__(self, img: Image.Image):
        self.img = img

    def enhance(self, factor: float) -> Image.Image:
        lut = [int(clamp(i * factor, 0, 255)) for i in range(256)]
        return self.img.point(lut)


def rotate_image_rgba(img: Image.Image, angle_deg: float) -> Image.Image:
    """
    Rotate RGBA image around center with transparent background.
    """
    if angle_deg % 360 == 0:
        return img
    return img.rotate(angle_deg, resample=Image.Resampling.BICUBIC, expand=True)


def paste_with_alpha(base: Image.Image, overlay: Image.Image, pos: Tuple[int, int]) -> None:
    """
    Paste overlay onto base at pos using alpha channel.
    """
    base.alpha_composite(overlay, dest=pos)


def calc_position(
    base_size: Tuple[int, int],
    overlay_size: Tuple[int, int],
    preset_key: Optional[str],
    manual_pos_px: Optional[Tuple[int, int]],
    margin: Tuple[int, int] = (10, 10),
) -> Tuple[int, int]:
    """
    Calculate position either from nine-grid preset or manual pixel position.
    """
    bw, bh = base_size
    ow, oh = overlay_size
    mx, my = margin
    if manual_pos_px is not None:
        # Ensure within bounds with margin
        x = clamp(manual_pos_px[0], mx, max(0, bw - ow - mx))
        y = clamp(manual_pos_px[1], my, max(0, bh - oh - my))
        return int(x), int(y)

    if preset_key in PRESET_POSITIONS:
        px, py = PRESET_POSITIONS[preset_key]
        # Map fractional positions to pixel coords with margin
        x_candidates = {
            0.0: mx,
            0.5: int((bw - ow) / 2),
            1.0: bw - ow - mx,
        }
        y_candidates = {
            0.0: my,
            0.5: int((bh - oh) / 2),
            1.0: bh - oh - my,
        }
        x = x_candidates.get(px, int((bw - ow) / 2))
        y = y_candidates.get(py, int((bh - oh) / 2))
        return int(x), int(y)

    # Default center
    return int((bw - ow) / 2), int((bh - oh) / 2)


def apply_watermark(
    base_img: Image.Image,
    settings: Dict[str, Any],
    preview_scale_factor: Optional[float] = None,
) -> Image.Image:
    """
    Apply either text or image watermark to base_img according to settings.
    settings keys:
      - type: "text" or "image"
      - opacity: 0..1
      - rotation_deg: float
      - position_preset: Optional[str]
      - manual_pos_px: Optional[Tuple[int,int]]  (in original pixel coordinates)
      - margin: Tuple[int,int]
    Text:
      - text, font_path, font_size, color_rgba, stroke_width, stroke_rgba, shadow_offset, shadow_rgba
    Image:
      - wm_image_path, wm_scale
    preview_scale_factor:
      - if manual_pos_px provided in preview scene coords, supply scale factor to convert to original pixels
    """
    img = base_img.convert("RGBA")
    typ = settings.get("type", "text")
    opacity = clamp(float(settings.get("opacity", 1.0)), 0.0, 1.0)
    rotation_deg = float(settings.get("rotation_deg", 0.0))
    position_preset = settings.get("position_preset")
    manual_pos_px = settings.get("manual_pos_px")
    margin = settings.get("margin", (10, 10))
    if manual_pos_px and preview_scale_factor and preview_scale_factor > 0:
        manual_pos_px = (int(manual_pos_px[0] / preview_scale_factor), int(manual_pos_px[1] / preview_scale_factor))

    if typ == "text":
        text = settings.get("text", "")
        font_family = settings.get("font_family")
        font_size = int(settings.get("font_size", 32))
        color_rgba = settings.get("color_rgba", (255, 255, 255, int(255 * opacity)))
        stroke_width = int(settings.get("stroke_width", 0))
        stroke_rgba = settings.get("stroke_rgba")
        shadow_offset = settings.get("shadow_offset", (0, 0))
        shadow_rgba = settings.get("shadow_rgba")

        font_bold = settings.get("font_bold", False)
        font_italic = settings.get("font_italic", False)
        
        wm = compose_text_watermark(
            text=text,
            font_family=font_family,
            font_size=font_size,
            color_rgba=(color_rgba[0], color_rgba[1], color_rgba[2], int(255 * opacity)),
            stroke_width=stroke_width,
            stroke_rgba=stroke_rgba,
            shadow_offset=shadow_offset,
            shadow_rgba=shadow_rgba,
            bold=font_bold,
            italic=font_italic,
        )
    else:
        wm_path = settings.get("wm_image_path")
        if not wm_path or not os.path.exists(wm_path):
            return img
        wm = Image.open(wm_path).convert("RGBA")
        scale = float(settings.get("wm_scale", 1.0))
        scale = max(0.01, scale)
        new_size = (max(1, int(wm.width * scale)), max(1, int(wm.height * scale)))
        wm = wm.resize(new_size, Image.Resampling.LANCZOS)
        if opacity < 1.0:
            alpha = wm.split()[-1]
            enhancer = ImageEnhanceBrightness(alpha)
            wm.putalpha(enhancer.enhance(opacity))

    # Rotation
    if rotation_deg % 360 != 0:
        wm = rotate_image_rgba(wm, rotation_deg)

    # Position
    pos = calc_position((img.width, img.height), (wm.width, wm.height), position_preset, manual_pos_px, margin=margin)

    # Composite
    out = img.copy()
    paste_with_alpha(out, wm, pos)
    return out


def export_image(
    base_img: Image.Image,
    settings: Dict[str, Any],
    export_opts: Dict[str, Any],
    preview_scale_factor: Optional[float] = None,
) -> Image.Image:
    """
    Apply watermark then optionally resize for export.
    export_opts:
      - format: "PNG" or "JPEG"
      - quality: int 0..100 (JPEG only)
      - resize: {"width": Optional[int], "height": Optional[int], "percent": Optional[float]}
    """
    composed = apply_watermark(base_img, settings, preview_scale_factor=preview_scale_factor)
    resize_opts = export_opts.get("resize", {})
    if resize_opts:
        composed = apply_resize(composed, resize_opts)
    return composed