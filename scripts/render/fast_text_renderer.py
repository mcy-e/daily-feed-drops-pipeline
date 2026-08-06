import logging
import pathlib
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont

from scripts.constants import (
    CONTENT_STYLE_PRESETS,
    MANIM_PIXEL_HEIGHT,
    MANIM_PIXEL_WIDTH,
)

logger = logging.getLogger(__name__)

FONT_SIZE_LARGE = 96
FONT_SIZE_MEDIUM = 72
FONT_SIZE_SMALL = 56
FONT_SIZE_NUMBER = 160

CARD_PADDING = 60
MAX_TEXT_WIDTH_RATIO = 0.82


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for path in font_paths:
        if pathlib.Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy: tuple, radius: int, fill: tuple) -> None:
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


def _create_text_frame(segment: dict, style: dict, width: int, height: int) -> Image.Image:
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    visual_type = segment.get("visual_type", "text")
    content = segment.get("visual_content", "")
    accent_rgb = _hex_to_rgb(style.get("accent_color", "#ffffff"))
    text_rgb = _hex_to_rgb(style.get("text_color", "#ffffff"))
    card_rgb = (10, 10, 30, 220)

    center_x = width // 2
    center_y = height // 2

    if visual_type == "number":
        num_font = _load_font(FONT_SIZE_NUMBER)
        label_font = _load_font(FONT_SIZE_SMALL)
        parts = str(content).split("\n", 1)
        number_text = parts[0].strip()
        label_text = parts[1].strip() if len(parts) > 1 else ""

        num_bbox = draw.textbbox((0, 0), number_text, font=num_font)
        num_w = num_bbox[2] - num_bbox[0]
        num_h = num_bbox[3] - num_bbox[1]

        card_h = num_h + 120 + (60 if label_text else 0)
        card_w = min(num_w + 120, int(width * MAX_TEXT_WIDTH_RATIO))
        cx = center_x - card_w // 2
        cy = center_y - card_h // 2
        _draw_rounded_rect(draw, (cx, cy, cx + card_w, cy + card_h), 32, card_rgb)

        draw.text((center_x, center_y - (30 if label_text else 0)), number_text,
                  fill=accent_rgb, font=num_font, anchor="mm")
        if label_text:
            draw.text((center_x, center_y + num_h // 2 + 20), label_text,
                      fill=text_rgb, font=label_font, anchor="mm")

    elif visual_type == "list":
        if isinstance(content, list):
            items = [str(i).strip().lstrip("•- ") for i in content if str(i).strip()]
        else:
            raw = content.split("\n") if "\n" in str(content) else str(content).split("|")
            items = [i.strip().lstrip("•- ") for i in raw if i.strip()]

        font = _load_font(FONT_SIZE_MEDIUM)
        line_h = FONT_SIZE_MEDIUM + 20
        card_h = len(items) * (line_h + 16) + CARD_PADDING * 2
        card_w = int(width * MAX_TEXT_WIDTH_RATIO)
        cx = center_x - card_w // 2
        cy = center_y - card_h // 2
        _draw_rounded_rect(draw, (cx, cy, cx + card_w, cy + card_h), 32, card_rgb)

        y = cy + CARD_PADDING
        for item in items:
            draw.text((cx + CARD_PADDING, y), f"• {item}", fill=text_rgb, font=font)
            y += line_h + 16

    else:
        font_size = FONT_SIZE_LARGE if len(str(content)) < 60 else FONT_SIZE_MEDIUM
        font = _load_font(font_size)
        max_chars = int((width * MAX_TEXT_WIDTH_RATIO) / (font_size * 0.55))
        lines = textwrap.wrap(str(content), width=max_chars)
        line_h = font_size + 16
        card_h = len(lines) * line_h + CARD_PADDING * 2
        card_w = int(width * MAX_TEXT_WIDTH_RATIO)
        cx = center_x - card_w // 2
        cy = center_y - card_h // 2
        _draw_rounded_rect(draw, (cx, cy, cx + card_w, cy + card_h), 32, card_rgb)

        y = cy + CARD_PADDING
        for line in lines:
            draw.text((center_x, y), line, fill=text_rgb, font=font, anchor="mt")
            y += line_h

    return img


def render_segment(
    segment: dict,
    content_type: str,
    duration: float,
    output_dir: pathlib.Path,
    quality: str = "l",
) -> str:
    """Render a text segment as a transparent MOV using PIL + FFmpeg."""
    output_dir.mkdir(parents=True, exist_ok=True)

    style = CONTENT_STYLE_PRESETS.get(content_type, {
        "text_color": "#ffffff", "accent_color": "#ffffff"
    })

    frame = _create_text_frame(segment, style, MANIM_PIXEL_WIDTH, MANIM_PIXEL_HEIGHT)
    frame_path = output_dir / f"seg_{segment['id']:02d}_frame.png"
    frame.save(str(frame_path), "PNG")

    output_path = str(output_dir / f"seg_{segment['id']:02d}.mov")

    fps = 30
    fade_frames = 15

    vf = (
        f"fade=t=in:st=0:d={fade_frames / fps}:alpha=1,"
        f"fade=t=out:st={max(0, duration - fade_frames / fps):.3f}:d={fade_frames / fps}:alpha=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(frame_path),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "qtrle",
        "-r", str(fps),
        "-pix_fmt", "argb",
        output_path,
    ]

    logger.info("Rendering text card for segment %d (%.2fs)", segment["id"], duration)
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("Text render failed: %s", exc.stderr[-500:])
        raise RuntimeError(f"Text render failed for segment {segment['id']}: {exc.stderr[-300:]}") from exc

    frame_path.unlink(missing_ok=True)
    logger.info("Segment %d rendered: %s", segment["id"], output_path)
    return output_path
