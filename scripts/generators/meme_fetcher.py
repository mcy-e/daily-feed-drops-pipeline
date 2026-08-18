import logging
import pathlib
import uuid
import random
import os
import io

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from scripts.constants import PROJECT_ROOT
from scripts.utils.retry import retry_with_backoff
from scripts.utils.gdrive import get_drive_service, download_json_file, upload_json_file, list_files_in_folder, download_file

from PIL import Image

logger = logging.getLogger(__name__)

def _get_used_memes_gdrive(service, folder_id: str) -> set[str]:
    if not service or not folder_id:
        return set()
    data = download_json_file(service, folder_id, "used_memes.json")
    if data and isinstance(data, list):
        return set(data)
    return set()

def _save_used_meme_gdrive(service, folder_id: str, url: str):
    if not service or not folder_id:
        return
    used = _get_used_memes_gdrive(service, folder_id)
    used.add(url)
    upload_json_file(service, folder_id, "used_memes.json", list(used))

def _fetch_from_gdrive(service, folder_id: str, dest_dir: pathlib.Path) -> dict:
    files = list_files_in_folder(service, folder_id, mime_type_prefix="image/")
    if not files:
        return None
        
    # Pick a random custom meme
    file = random.choice(files)
    file_id = file['id']
    file_name = file['name']
    
    filename = f"meme_{uuid.uuid4().hex[:6]}.jpg"
    image_path = dest_dir / filename
    
    logger.info(f"Downloading custom meme from Drive: {file_name}")
    if download_file(service, file_id, str(image_path)):
        return {
            "id": 1,
            "narration": "Custom Meme",
            "visual_type": "image",
            "visual_content": "Custom Meme",
            "image_needed": False,
            "image_query": "",
            "image_path": str(image_path),
            "pause_after": 8.0,
            "gdrive_meme_id": file_id # We will delete this later
        }
    return None

def _fetch_from_internet(dest_dir: pathlib.Path, used_memes: set) -> dict:
    subreddits = "dankmemes+shitposting+meme+me_irl+funny+gaming"
    logger.info("Fetching batch of memes from meme-api.com")
    resp = requests.get(f"https://meme-api.com/gimme/{subreddits}/20", timeout=30, verify=False)
    resp.raise_for_status()
    data = resp.json()
    
    # We allow dark humor, but block NSFW/Spoiler entirely for YouTube safety
    memes = [m for m in data.get("memes", []) if not m.get("nsfw") and not m.get("spoiler")]
    
    # Only ban extreme ToS violations
    banned_words = {"nsfw", "porn", "nude", "cp", "rape", "suicide"}
    
    for meme in memes:
        image_url = meme.get("url", "")
        title = meme.get("title", "Meme").strip()
        title_lower = title.lower()
        
        if any(banned in title_lower for banned in banned_words):
            continue
            
        if image_url in used_memes:
            continue
        
        try:
            img_resp = requests.get(image_url, timeout=60, verify=False)
            img_resp.raise_for_status()
            
            with Image.open(io.BytesIO(img_resp.content)) as img:
                w, h = img.size
                if h / w > 1.8: # Reject extremely tall memes
                    continue
                    
            filename = f"meme_{uuid.uuid4().hex[:6]}.jpg"
            image_path = dest_dir / filename
            image_path.write_bytes(img_resp.content)
            
            return {
                "id": 1,
                "narration": title,
                "visual_type": "image",
                "visual_content": title,
                "image_needed": False,
                "image_query": "",
                "image_path": str(image_path),
                "pause_after": 8.0,
                "url": image_url # For history tracking
            }
        except Exception as e:
            logger.warning("Failed to process meme: %s", e)
            
    return None

@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def fetch_meme_script(dest_dir: pathlib.Path, force: bool = False) -> dict:
    """Fetch 1 meme either from Drive or Internet and build script dict."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    service = get_drive_service()
    memes_folder_id = os.environ.get("GDRIVE_MEMES_FOLDER_ID")
    
    used_memes = set() if force else _get_used_memes_gdrive(service, memes_folder_id)
    
    segment = None
    
    # 50/50 Roll
    use_drive = random.choice([True, False])
    
    if use_drive:
        logger.info("50/50 Roll: Checking Google Drive for custom meme")
        segment = _fetch_from_gdrive(service, memes_folder_id, dest_dir)
        
    if not segment:
        logger.info("Fetching from Internet (Either rolled Internet, or Drive was empty/failed)")
        segment = _fetch_from_internet(dest_dir, used_memes)
        
        if not segment and not use_drive:
            # Fallback to drive if internet failed and we didn't try drive yet
            logger.info("Internet failed. Falling back to Google Drive")
            segment = _fetch_from_gdrive(service, memes_folder_id, dest_dir)
            
    if not segment:
        raise Exception("Failed to fetch meme from both Drive and Internet.")
        
    # Save history if it's an internet meme
    if "url" in segment:
        _save_used_meme_gdrive(service, memes_folder_id, segment["url"])

    title = segment.get("narration", "Meme of the Day")
    script = {
        "title": title[:80],
        "description": f"😂 {title} #meme #funny #viral #shorts",
        "tags": ["meme", "funny", "viral", "shorts", "gaming"],
        "segments": [segment],
    }
    logger.info("Built meme_recap script")
    return script

def fetch_meme_script_simple() -> dict | None:
    """Wrapper that fetches one meme without requiring a dest_dir argument."""
    import tempfile
    dest = pathlib.Path(tempfile.mkdtemp()) / "memes"
    dest.mkdir(parents=True, exist_ok=True)
    try:
        return fetch_meme_script(dest_dir=dest)
    except Exception as exc:
        logger.error("fetch_meme_script_simple failed: %s", exc)
        return None