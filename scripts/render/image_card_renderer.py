import logging
import pathlib

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

TARGET_W = 1080
TARGET_H = 1920
CARD_MARGIN = 48
CARD_MAX_WIDTH_RATIO = 0.88

# Style per content type: meme, center, subtitle
CARD_STYLES = {
    "meme_recap": "meme",
    "explained_topic": "subtitle",
    "quiz_riddle": "center",
    "dark_facts": "meme",
    "would_you_rather": "center",
    "football_trivia": "subtitle",
    "viral_news": "subtitle",
    "motivation_content": "center",
}

ACCENT_COLORS = {
    "dark_facts": (255, 51, 51),
    "would_you_rather": (108, 99, 255),
    "football_trivia": (149, 213, 178),
    "viral_news": (255, 68, 68),
    "explained_topic": (79, 195, 247),
    "meme_recap": (255, 255, 255),
    "quiz_riddle": (155, 89, 182),
    "motivation_content": (255, 179, 71),
}


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for p in candidates:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if draw.textlength(test, font=font) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _outline_text(draw: ImageDraw.ImageDraw, pos: tuple, text: str, font, fill: tuple, outline: tuple, width: int = 4) -> None:
    x, y = pos
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def _paste_rgba(base: Image.Image, overlay_rgba: Image.Image, position: tuple) -> None:
    """Paste an RGBA image onto an RGB base using the alpha channel as mask."""
    r, g, b, a = overlay_rgba.split()
    rgb = Image.merge("RGB", (r, g, b))
    base.paste(rgb, position, mask=a)


def _fill_frame(image_path: str) -> Image.Image:
    """Open and crop-scale the source image to exactly TARGET_W x TARGET_H."""
    img = Image.open(image_path).convert("RGB")
    img_ratio = img.width / img.height
    target_ratio = TARGET_W / TARGET_H
    if img_ratio > target_ratio:
        new_h = TARGET_H
        new_w = int(img_ratio * TARGET_H)
    else:
        new_w = TARGET_W
        new_h = int(TARGET_W / img_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - TARGET_W) // 2
    top = (new_h - TARGET_H) // 2
    return img.crop((left, top, left + TARGET_W, top + TARGET_H))


def render_image_card(
    image_path: str,
    text: str,
    content_type: str,
    output_path: str,
) -> str:
    """Composite segment text onto a real photo, meme-card style. Returns output_path."""
    style = CARD_STYLES.get(content_type, "subtitle")
    accent = ACCENT_COLORS.get(content_type, (255, 255, 255))

    img = _fill_frame(image_path)
    draw = ImageDraw.Draw(img)

    max_text_w = int(TARGET_W * CARD_MAX_WIDTH_RATIO)
    font_size = 68
    font = _load_font(font_size)
    lines = _wrap_lines(text, font, max_text_w, draw)

    while len(lines) > 5 and font_size > 42:
        font_size -= 6
        font = _load_font(font_size)
        lines = _wrap_lines(text, font, max_text_w, draw)

    line_h = font_size + 16
    block_h = len(lines) * line_h + CARD_MARGIN * 2

    if style == "meme":
        # Dark bar at bottom, white outlined text — classic meme look
        y_start = TARGET_H - block_h - 72
        bar = Image.new("RGBA", (TARGET_W, block_h + 16), (0, 0, 0, 170))
        _paste_rgba(img, bar, (0, y_start))
        y = y_start + CARD_MARGIN
        for line in lines:
            lw = int(draw.textlength(line, font=font))
            x = (TARGET_W - lw) // 2
            _outline_text(draw, (x, y), line, font, fill=(255, 255, 255), outline=(0, 0, 0))
            y += line_h

    elif style == "center":
        # Frosted glass panel in the vertical center
        panel_top = TARGET_H // 2 - block_h // 2 - 8
        panel_bottom = panel_top + block_h + 16
        region = img.crop((CARD_MARGIN, panel_top, TARGET_W - CARD_MARGIN, panel_bottom))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=20))
        img.paste(blurred, (CARD_MARGIN, panel_top))
        dark = Image.new("RGBA", (TARGET_W - CARD_MARGIN * 2, block_h + 16), (0, 0, 0, 175))
        _paste_rgba(img, dark, (CARD_MARGIN, panel_top))
        draw = ImageDraw.Draw(img)
        y = panel_top + CARD_MARGIN
        for line in lines:
            lw = int(draw.textlength(line, font=font))
            x = (TARGET_W - lw) // 2
            _outline_text(draw, (x, y), line, font, fill=(255, 255, 255), outline=(0, 0, 0))
            y += line_h

    else:
        # Subtitle bar — accent-colored text at very bottom
        y_start = TARGET_H - block_h - 40
        bar = Image.new("RGBA", (TARGET_W, block_h + 24), (0, 0, 0, 200))
        _paste_rgba(img, bar, (0, y_start))
        draw = ImageDraw.Draw(img)
        y = y_start + CARD_MARGIN
        for line in lines:
            lw = int(draw.textlength(line, font=font))
            x = (TARGET_W - lw) // 2
            _outline_text(draw, (x, y), line, font, fill=accent, outline=(0, 0, 0))
            y += line_h

    img.save(output_path, "JPEG", quality=92)
    logger.info("Image card rendered: %s", output_path)
    return output_path
