import logging
import os
import pathlib
import random
import uuid
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from scripts.constants import PEXELS_API_KEY_ENV_VAR, PEXELS_VIDEO_SEARCH_URL
from scripts.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

BROLL_QUERIES = [
    "satisfying loop",
    "abstract satisfying",
    "kinetic sand",
    "nature drone vertical",
    "city hyperlapse vertical",
    "neon abstract loop",
    "paint mixing satisfying",
    "gaming racing",
    "fluid simulation loop"
]

@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def fetch_aesthetic_broll(dest_dir: pathlib.Path) -> str:
    """Download a satisfying vertical background video from Pexels."""
    api_key = os.getenv(PEXELS_API_KEY_ENV_VAR)
    if not api_key:
        raise ValueError(f"{PEXELS_API_KEY_ENV_VAR} is not set")

    dest_dir.mkdir(parents=True, exist_ok=True)
    query = random.choice(BROLL_QUERIES)
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 15, "orientation": "portrait", "size": "medium"}

    logger.info("Searching Pexels Video for: %s", query)
    resp = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params, timeout=30, verify=False)
    resp.raise_for_status()
    videos = resp.json().get("videos", [])

    if not videos:
        params["query"] = "abstract vertical loop"
        resp = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params, timeout=30, verify=False)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        
    if not videos:
        raise RuntimeError("No Pexels videos found for B-Roll")

    # Filter to clips >= 60s so the video never visibly loops during a short
    long_videos = [v for v in videos if v.get("duration", 0) >= 60]
    video_meta = random.choice(long_videos) if long_videos else random.choice(videos)
    video_files = video_meta.get("video_files", [])
    if not video_files:
        raise RuntimeError("Pexels video has no files")
        
    video_files.sort(key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)
    video_url = video_files[0]["link"]

    filename = f"broll_{uuid.uuid4().hex[:8]}.mp4"
    dest_path = dest_dir / filename
    
    logger.info("Downloading Pexels B-Roll from %s", video_url)
    with requests.get(video_url, stream=True, timeout=120, verify=False) as r:
        r.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    logger.info("Downloaded Pexels B-Roll to %s", dest_path)
    return str(dest_path)
