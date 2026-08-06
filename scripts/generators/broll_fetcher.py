import logging
import os
import pathlib
import random
import uuid
import subprocess
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from scripts.constants import PEXELS_API_KEY_ENV_VAR, PEXELS_VIDEO_SEARCH_URL
from scripts.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

BROLL_QUERIES = [
    "minecraft parkour gameplay",
    "minecraft satisfying build",
    "gta v racing gameplay",
    "subway surfers gameplay",
    "satisfying kinetic sand",
    "satisfying soap cutting",
    "abstract 3d loop satisfying",
]

@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def _download_video(url: str, dest_path: pathlib.Path):
    with requests.get(url, stream=True, timeout=60, verify=False) as r:
        r.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def fetch_aesthetic_broll(dest_dir: pathlib.Path) -> str:
    """Download multiple satisfying vertical videos from Pexels and concatenate them for a non-repeating B-Roll."""
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

    if len(videos) < 3:
        params["query"] = "abstract vertical loop"
        resp = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params, timeout=30, verify=False)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        
    if not videos:
        raise RuntimeError("No Pexels videos found for B-Roll")

    # Pick 3 random videos to concatenate so it doesn't repeat
    selected = random.sample(videos, min(3, len(videos)))
    downloaded_paths = []

    for idx, video_meta in enumerate(selected):
        video_files = video_meta.get("video_files", [])
        if not video_files:
            continue
        video_files.sort(key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)
        video_url = video_files[0]["link"]
        dest_path = dest_dir / f"raw_broll_{idx}.mp4"
        logger.info("Downloading Pexels clip %d: %s", idx, video_url)
        _download_video(video_url, dest_path)
        downloaded_paths.append(dest_path)

    if not downloaded_paths:
        raise RuntimeError("Failed to download any B-Roll clips")

    if len(downloaded_paths) == 1:
        return str(downloaded_paths[0])

    # Concatenate the downloaded clips using ffmpeg filter to ensure same resolution
    final_path = dest_dir / f"final_broll_{uuid.uuid4().hex[:8]}.mp4"
    list_path = dest_dir / "concat_list.txt"
    
    with open(list_path, "w", encoding="utf-8") as f:
        for p in downloaded_paths:
            escaped = str(p.resolve()).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(final_path)
    ]
    logger.info("Concatenating %d B-Roll clips", len(downloaded_paths))
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    return str(final_path)
