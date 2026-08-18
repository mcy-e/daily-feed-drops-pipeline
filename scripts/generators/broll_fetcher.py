import logging
import os
import pathlib
import random
import uuid
import subprocess

from scripts.utils.retry import retry_with_backoff
from scripts.utils.gdrive import get_drive_service, list_files_in_folder, download_file

logger = logging.getLogger(__name__)

GAMING_VIDEOS = [
    "https://www.youtube.com/watch?v=n_Dv4JMmAO8",
    "https://www.youtube.com/watch?v=aHkLqNn_2dM",
    "https://www.youtube.com/watch?v=f2nNnJgA-tY",
    "https://www.youtube.com/watch?v=Wji-BZ0oC1w",
    "https://www.youtube.com/watch?v=XhxwGJaGqL8"
]

def _fetch_broll_gdrive(dest_dir: pathlib.Path) -> str | None:
    service = get_drive_service()
    folder_id = os.environ.get("GDRIVE_BROLL_FOLDER_ID")
    if not service or not folder_id:
        return None
        
    files = list_files_in_folder(service, folder_id, mime_type_prefix="video/")
    if not files:
        logger.info("No videos found in Drive B-Roll folder.")
        return None
        
    file = random.choice(files)
    file_id = file['id']
    file_name = file['name']
    
    final_path = dest_dir / f"broll_gdrive_{uuid.uuid4().hex[:8]}.mp4"
    logger.info(f"Downloading B-Roll from Drive: {file_name}")
    
    if download_file(service, file_id, str(final_path)):
        return str(final_path)
    return None

@retry_with_backoff(max_retries=3, delays=(5, 10, 15))
def fetch_aesthetic_broll(dest_dir: pathlib.Path) -> str:
    """Download a random gaming B-Roll from Drive or YouTube."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Try Google Drive first
    drive_broll = _fetch_broll_gdrive(dest_dir)
    if drive_broll:
        return drive_broll
        
    # 2. Fallback to YouTube
    video_url = random.choice(GAMING_VIDEOS)
    final_path = dest_dir / f"broll_gaming_{uuid.uuid4().hex[:8]}.mp4"
    logger.info("Fetching continuous 65s gaming B-Roll from %s", video_url)
    
    start_time = random.randint(300, 2700)
    cmd = [
        "yt-dlp",
        "--force-ipv4",
        "--format", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
        "--download-sections", f"*{start_time}-{start_time + 65}",
        "--output", str(final_path),
        "--force-keyframes-at-cuts",
        video_url
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return str(final_path)
    except subprocess.CalledProcessError as exc:
        logger.error("yt-dlp failed: %s. Generating black video fallback.", exc.stderr)
        cmd_fallback = [
            "ffmpeg", "-y", "-f", "lavfi", 
            "-i", "color=c=black:s=1080x1920:r=30:d=65", 
            "-c:v", "libx264", "-preset", "fast", 
            str(final_path)
        ]
        subprocess.run(cmd_fallback, capture_output=True, check=True)
        return str(final_path)
