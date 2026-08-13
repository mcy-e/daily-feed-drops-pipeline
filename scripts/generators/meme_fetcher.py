import logging
import pathlib
import uuid

import requests

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from scripts.constants import MEME_API_URL, PROJECT_ROOT
from scripts.utils.retry import retry_with_backoff

from PIL import Image
import io
import json

logger = logging.getLogger(__name__)

USED_MEMES_FILE = PROJECT_ROOT / "data" / "used_memes.json"

def _load_used_memes() -> set[str]:
    if USED_MEMES_FILE.exists():
        try:
            with open(USED_MEMES_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def _save_used_meme(url: str):
    used = _load_used_memes()
    used.add(url)
    USED_MEMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USED_MEMES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(used), f)


@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def fetch_meme_script(dest_dir: pathlib.Path, force: bool = False) -> dict:
    """Fetch 3 memes from meme-api.com and build a structured script dict."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    segments = []
    idx = 1
    used_memes = set() if force else _load_used_memes()
    if force:
        logger.info("Force mode: skipping meme deduplication history check")
    
    while len(segments) < 1:
        logger.info("Fetching batch of memes from meme-api.com")
        # Overriding MEME_API_URL to fetch 10 from safe subreddits
        resp = requests.get("https://meme-api.com/gimme/wholesomememes+me_irl+funny+gaming+memes/10", timeout=30, verify=False)
        resp.raise_for_status()
        data = resp.json()
        
        memes = [m for m in data.get("memes", []) if not m.get("nsfw") and not m.get("spoiler")]
        
        # Keywords to ban
        banned_words = {"god", "jesus", "allah", "religion", "bible", "quran", "church", "mosque", "sex", "porn", "nude", "nsfw", "kill", "suicide", "murder"}
        
        for meme in memes:
            if len(segments) >= 3:
                break
                
            image_url = meme.get("url", "")
            title = meme.get("title", "Meme").strip()
            title_lower = title.lower()
            
            if any(banned in title_lower for banned in banned_words):
                logger.info("Skipping meme due to banned keyword in title: %s", title)
                continue
                
            if image_url in used_memes:
                logger.info("Skipping already used meme: %s", title)
                continue
            
            try:
                img_resp = requests.get(image_url, timeout=60, verify=False)
                img_resp.raise_for_status()
                
                # Check aspect ratio
                with Image.open(io.BytesIO(img_resp.content)) as img:
                    w, h = img.size
                    if h / w > 1.5:
                        logger.info("Skipping tall meme '%s' (w:%d, h:%d, ratio:%.2f)", title, w, h, h/w)
                        continue
                        
                filename = f"meme_{idx}_{uuid.uuid4().hex[:6]}.jpg"
                image_path = dest_dir / filename
                image_path.write_bytes(img_resp.content)
                
                segments.append({
                    "id": idx,
                    "narration": title,
                    "visual_type": "image",
                    "visual_content": title,
                    "image_needed": False,
                    "image_query": "",
                    "image_path": str(image_path),
                    "pause_after": 8.0,
                })
                used_memes.add(image_url)
                _save_used_meme(image_url)
                idx += 1
            except Exception as e:
                logger.warning("Failed to fetch or process meme '%s': %s", title, e)

    script = {
        "title": "Meme of the Day",
        "segments": segments,
    }
    logger.info("Built meme_recap script with %d meme", len(segments))
    return script


def fetch_meme_script_simple() -> dict | None:
    """Wrapper that fetches one meme without requiring a dest_dir argument."""
    import tempfile, pathlib
    dest = pathlib.Path(tempfile.mkdtemp()) / "memes"
    dest.mkdir(parents=True, exist_ok=True)
    try:
        script = fetch_meme_script(dest_dir=dest)
        if not script or not script.get("segments"):
            return None
        # Keep only the first segment
        script["segments"] = script["segments"][:1]
        seg = script["segments"][0]
        title = seg.get("narration", "Meme of the Day")
        script["title"] = title[:80]
        script["description"] = f"😂 {title} #meme #funny #viral #shorts"
        script["tags"] = ["meme", "funny", "viral", "shorts", "gaming"]
        return script
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("fetch_meme_script_simple failed: %s", exc)
        return None