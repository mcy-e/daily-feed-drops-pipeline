import logging
import pathlib

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

TARGET_W = 1080
TARGET_H = 1920
CARD_W = 940
CARD_MARGIN = 40

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
    """Render a classic meme-style card (white box, black text, image below) on a transparent 1080x1920 canvas."""
    # Ensure output is PNG for transparency
    if output_path.lower().endswith(".jpg") or output_path.lower().endswith(".jpeg"):
        output_path = output_path.rsplit(".", 1)[0] + ".png"

    # 1. Load and resize the photo
    try:
        photo = Image.open(image_path).convert("RGB")
    except Exception as e:
        logger.warning("Could not open image %s: %s", image_path, e)
        photo = Image.new("RGB", (CARD_W, 600), (50, 50, 50))
        
    ratio = photo.height / photo.width
    new_h = int(CARD_W * ratio)
    
    # Cap image height so it doesn't take up the whole screen vertically
    if new_h > 1000:
        new_h = 1000
        new_w = int(new_h / ratio)
        photo = photo.resize((new_w, new_h), Image.LANCZOS)
        # Pad sides with black to reach CARD_W
        padded = Image.new("RGB", (CARD_W, new_h), (0, 0, 0))
        padded.paste(photo, ((CARD_W - new_w) // 2, 0))
        photo = padded
    else:
        photo = photo.resize((CARD_W, new_h), Image.LANCZOS)

    # 2. Prepare the text block
    font_size = 56
    font = _load_font(font_size)
    # Temporary draw object for measuring
    temp_img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(temp_img)
    
    max_text_w = CARD_W - (CARD_MARGIN * 2)
    lines = _wrap_lines(text, font, max_text_w, draw)
    while len(lines) > 8 and font_size > 36:
        font_size -= 4
        font = _load_font(font_size)
        lines = _wrap_lines(text, font, max_text_w, draw)
        
    line_h = font_size + 12
    text_block_h = len(lines) * line_h + (CARD_MARGIN * 2)

    # 3. Create the white meme card
    card_h = text_block_h + photo.height
    card = Image.new("RGB", (CARD_W, card_h), (255, 255, 255))
    draw = ImageDraw.Draw(card)
    
    # Draw text
    y = CARD_MARGIN
    for line in lines:
        lw = int(draw.textlength(line, font=font))
        x = (CARD_W - lw) // 2
        draw.text((x, y), line, font=font, fill=(0, 0, 0))
        y += line_h
        
    # Paste photo directly below text
    card.paste(photo, (0, text_block_h))
    
    # 4. Paste card into center of transparent 1080x1920 canvas
    canvas = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    paste_x = (TARGET_W - CARD_W) // 2
    paste_y = (TARGET_H - card_h) // 2
    
    # Optional: add a slight drop shadow or rounded corners, but simple paste is fine
    canvas.paste(card, (paste_x, paste_y))
    
    canvas.save(output_path, "PNG")
    logger.info("Meme card rendered: %s", output_path)
    return output_path
