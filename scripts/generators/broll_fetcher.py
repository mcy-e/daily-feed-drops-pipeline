import logging
import os
import pathlib
import random
import uuid
import subprocess

from scripts.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# A large variety of 1+ hour gaming and satisfying gameplay videos
GAMING_VIDEOS = [
    # Minecraft Parkour
    "https://www.youtube.com/watch?v=n_Dv4JMmAO8",
    "https://www.youtube.com/watch?v=aHkLqNn_2dM",
    "https://www.youtube.com/watch?v=J3sA0oVnQ90",
    "https://www.youtube.com/watch?v=XoQdFzQJ-1w",
    
    # GTA V Racing / Parkour
    "https://www.youtube.com/watch?v=f2nNnJgA-tY",
    "https://www.youtube.com/watch?v=Wji-BZ0oC1w",
    "https://www.youtube.com/watch?v=Kz6XqO1e1fM",
    
    # Subway Surfers / Mobile
    "https://www.youtube.com/watch?v=o0v-m_21EHU",
    "https://www.youtube.com/watch?v=ehvG7L-MIEg",
    
    # Satisfying / ASMR / Kinetic Sand
    "https://www.youtube.com/watch?v=XhxwGJaGqL8",
    "https://www.youtube.com/watch?v=jZ1S0uA56nE",
    "https://www.youtube.com/watch?v=o-YBDTqX_ZU",
]

@retry_with_backoff(max_retries=3, delays=(5, 10, 15))
def fetch_aesthetic_broll(dest_dir: pathlib.Path) -> str:
    """Download a random 65-second clip from a 1-hour gaming video using yt-dlp."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    video_url = random.choice(GAMING_VIDEOS)
    
    final_path = dest_dir / f"broll_gaming_{uuid.uuid4().hex[:8]}.mp4"
    logger.info("Fetching continuous 65s gaming B-Roll from %s", video_url)
    
    # We want a random 65s chunk. We'll grab from somewhere between minute 5 and minute 45.
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
