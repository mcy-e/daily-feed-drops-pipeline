import datetime
import io
import logging
import os
import pathlib
import random
import uuid

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from PIL import Image

from scripts.utils.gdrive import (
    delete_file,
    download_file,
    get_drive_service,
    list_files,
)

logger = logging.getLogger(__name__)

# Subreddits to pull from — shuffled each run for variety
_SUBREDDITS = [
    # English & Edgy/Dank
    "dankmemes", "shitposting", "HolUp", "dank_meme", "2meirl4meirl",
    "SipsTea", "Discordmemes", "Offensivejokes", "ImFinnaGoToHell",
    "cursedcomments", "meme", "memes",
    
    # International / Multi-language
    "ich_iel",          # German
    "moi_dlvv",         # French
    "yo_elvr",          # Spanish
    "ani_bm",           # Hebrew
    "ik_ihe",           # Dutch
    "eu_nvr",           # Portuguese
    "Polska_wpz",       # Polish
    "LatinoPeopleTwitter",
    "MemeItaliani",
    "memesESP",
]

# Only block hard ToS violations — dark humour is allowed
_BANNED = {"porn", "nude", "nsfw", "rape", "cp", "suicide", "selfharm"}



# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_safe(title: str, nsfw: bool, spoiler: bool) -> bool:
    if nsfw or spoiler:
        return False
    tl = title.lower()
    return not any(b in tl for b in _BANNED)


def _download_image(url: str, dest: pathlib.Path) -> str | None:
    try:
        r = requests.get(url, timeout=30, verify=False)
        r.raise_for_status()
        
        # Verify and re-encode image to ensure 100% ffmpeg compatibility
        with Image.open(io.BytesIO(r.content)) as img:
            w, h = img.size
            if w == 0 or h / w > 2.0:
                return None
                
            # Convert to RGB (drops alpha/transparency from PNG/WebP) to ensure standard JPG
            rgb_img = img.convert("RGB")
            rgb_img.save(dest, format="JPEG", quality=90)
            
        return str(dest)
    except Exception as exc:
        logger.debug("Image download failed (%s): %s", url, exc)
        return None


# ── Custom Drive meme (25% chance per run) ───────────────────────────────────

def _fetch_custom_drive(service, folder_id: str, dest_dir: pathlib.Path) -> dict | None:
    images = [f for f in list_files(service, folder_id, mime_prefix="image/")]
    if not images:
        logger.info("Custom memes folder is empty.")
        return None

    chosen = random.choice(images)
    dest = dest_dir / f"custom_{uuid.uuid4().hex[:6]}.jpg"
    if not download_file(service, chosen["id"], str(dest)):
        return None

    logger.info("Using custom Drive meme: %s", chosen["name"])

    return {
        "image_path": str(dest),
        "title": pathlib.Path(chosen["name"]).stem,
        "source": "drive",
        "gdrive_file_id": chosen["id"],
    }


# ── Internet meme (meme-api + Reddit JSON fallback) ──────────────────────────

def _fetch_internet(dest_dir: pathlib.Path) -> dict | None:
    subs = random.sample(_SUBREDDITS, min(5, len(_SUBREDDITS)))
    query = "+".join(subs)

    # Primary: meme-api.com
    try:
        r = requests.get(
            f"https://meme-api.com/gimme/{query}/30",
            timeout=20, verify=False,
        )
        r.raise_for_status()
        for m in r.json().get("memes", []):
            if not _is_safe(m.get("title", ""), m.get("nsfw", False), m.get("spoiler", False)):
                continue
            url = m.get("url", "")
            if not url:
                continue
            path = _download_image(url, dest_dir / f"meme_{uuid.uuid4().hex[:6]}.jpg")
            if path:
                return {"image_path": path, "title": m.get("title", "Meme")[:80], "source": "internet"}
    except Exception as exc:
        logger.warning("meme-api.com failed: %s", exc)

    # Fallback: direct Reddit JSON (works without API key)
    for sub in subs:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json?limit=30",
                headers={"User-Agent": "DailyFeedDrops/2.0"},
                timeout=15, verify=False,
            )
            for post in r.json()["data"]["children"]:
                d = post["data"]
                if not _is_safe(d.get("title", ""), d.get("over_18", False), d.get("spoiler", False)):
                    continue
                url = d.get("url", "")
                if not url.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                path = _download_image(url, dest_dir / f"meme_{uuid.uuid4().hex[:6]}.jpg")
                if path:
                    return {"image_path": path, "title": d.get("title", "Meme")[:80], "source": "internet"}
        except Exception as exc:
            logger.debug("Reddit fallback r/%s failed: %s", sub, exc)

    return None


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_meme(dest_dir: pathlib.Path) -> dict | None:
    """Fetch one meme image.

    Logic:
    - 25% chance per run: check the custom Drive folder and use it if populated.
      (Since pipeline runs 4x/day, this averages to 1 custom meme per day).
    - All other runs (and when Drive is empty): fetch from internet meme APIs.
    - Returns a dict with ``image_path``, ``title``, ``source``, and optionally
      ``gdrive_file_id`` (set when a Drive meme was used — delete after delivery).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    service = get_drive_service()
    folder_id = os.environ.get("GDRIVE_MEMES_FOLDER_ID")

    # 25% chance to attempt loading from Drive
    if service and folder_id and random.random() < 0.25:
        result = _fetch_custom_drive(service, folder_id, dest_dir)
        if result:
            return result
        logger.info("Custom folder empty or unavailable — falling back to internet.")

    logger.info("Fetching internet meme.")
    return _fetch_internet(dest_dir)


def delete_custom_meme_from_drive(meme: dict):
    """Call this AFTER successful video delivery to remove the file from Drive."""
    file_id = meme.get("gdrive_file_id")
    if not file_id:
        return
    service = get_drive_service()
    if service:
        delete_file(service, file_id)