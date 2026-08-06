import logging
import os
import pathlib
import random
import uuid
import subprocess

from scripts.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# List of 1+ hour Minecraft Parkour / Satisfying Gameplay videos on YouTube
GAMING_VIDEOS = [
    "https://www.youtube.com/watch?v=n_Dv4JMmAO8", # Minecraft parkour 1 hr
    "https://www.youtube.com/watch?v=aHkLqNn_2dM", # Minecraft parkour no copyright
    "https://www.youtube.com/watch?v=J3sA0oVnQ90", # Minecraft parkour
]

@retry_with_backoff(max_retries=3, delays=(5, 10, 15))
def fetch_aesthetic_broll(dest_dir: pathlib.Path) -> str:
    """Download a random 60-second clip from a 1-hour gaming video using yt-dlp."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    video_url = random.choice(GAMING_VIDEOS)
    
    final_path = dest_dir / f"broll_gaming_{uuid.uuid4().hex[:8]}.mp4"
    logger.info("Fetching continuous 60s gaming B-Roll from %s", video_url)
    
    # We want a random 60s chunk. We'll grab from somewhere between minute 5 and minute 45.
    start_time = random.randint(300, 2700)
    
    # yt-dlp can download just a section using --download-sections
    cmd = [
        "yt-dlp",
        "--format", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
        "--download-sections", f"*{start_time}-{start_time + 65}",
        "--output", str(final_path),
        "--force-keyframes-at-cuts",
        video_url
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("yt-dlp failed: %s", exc.stderr)
        raise RuntimeError("Failed to download gaming B-roll") from exc
        
    return str(final_path)
