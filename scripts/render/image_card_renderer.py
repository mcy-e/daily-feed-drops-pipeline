import logging
import pathlib

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

CARD_W = 700
CARD_MARGIN = 36


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


def render_image_card(
    image_path: str,
    text: str,
    content_type: str,
    output_path: str,
) -> str:
    """Render a meme-style card (text on top, image below) and save ONLY the card as PNG.
    No full-frame canvas — the card is composited directly onto B-Roll by ffmpeg overlay."""
    if not output_path.lower().endswith(".png"):
        output_path = output_path.rsplit(".", 1)[0] + ".png"

    # Load and resize the photo to card width
    try:
        photo = Image.open(image_path).convert("RGB")
    except Exception as e:
        logger.warning("Could not open image %s: %s", image_path, e)
        photo = Image.new("RGB", (CARD_W, 400), (50, 50, 50))

    ratio = photo.height / photo.width
    photo_h = int(CARD_W * ratio)

    # Keep photo height compact so card fits in top third of a 1920px reel
    if photo_h > 500:
        photo_h = 500
        photo_w = int(photo_h / ratio)
        photo = photo.resize((photo_w, photo_h), Image.LANCZOS)
        padded = Image.new("RGB", (CARD_W, photo_h), (0, 0, 0))
        padded.paste(photo, ((CARD_W - photo_w) // 2, 0))
        photo = padded
    else:
        photo = photo.resize((CARD_W, photo_h), Image.LANCZOS)

    # Build the text block
    font_size = 52
    font = _load_font(font_size)
    temp_img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(temp_img)
    max_text_w = CARD_W - (CARD_MARGIN * 2)
    lines = _wrap_lines(text, font, max_text_w, draw)

    while len(lines) > 7 and font_size > 32:
        font_size -= 4
        font = _load_font(font_size)
        lines = _wrap_lines(text, font, max_text_w, draw)

    line_h = font_size + 14
    text_block_h = len(lines) * line_h + (CARD_MARGIN * 2)

    # Compose the card: white background, black text on top, photo below
    card_h = text_block_h + photo_h
    card = Image.new("RGB", (CARD_W, card_h), (255, 255, 255))
    draw = ImageDraw.Draw(card)

    y = CARD_MARGIN
    for line in lines:
        lw = int(draw.textlength(line, font=font))
        x = (CARD_W - lw) // 2
        draw.text((x, y), line, font=font, fill=(20, 20, 20))
        y += line_h

    card.paste(photo, (0, text_block_h))

    # Save just the card — no full-frame canvas, no black borders
    card.save(output_path, "PNG")
    logger.info("Card rendered: %s (%dx%d)", output_path, CARD_W, card_h)
    return output_path
