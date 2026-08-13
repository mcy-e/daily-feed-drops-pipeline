import pathlib, random, subprocess, logging, os
import requests
from scripts.constants import PEXELS_API_KEY_ENV_VAR

logger = logging.getLogger(__name__)

def fetch_pexels_fallback_video(dest_dir: pathlib.Path) -> str:
    dest_dir.mkdir(parents=True, exist_ok=True)
    api_key = os.getenv(PEXELS_API_KEY_ENV_VAR)
    if not api_key:
        raise ValueError("No Pexels API key")
        
    query = random.choice(["gta", "car driving", "minecraft", "parkour", "abstract looping", "neon looping"])
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=15"
    headers = {"Authorization": api_key}
    
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    
    videos = data.get("videos", [])
    if not videos:
        raise ValueError("No Pexels fallback videos found")
        
    video = random.choice(videos)
    video_files = video.get("video_files", [])
    # Get highest res mp4
    video_files = [f for f in video_files if f.get("file_type") == "video/mp4"]
    if not video_files:
        raise ValueError("No mp4 files in Pexels video")
        
    video_files.sort(key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)
    best_file = video_files[0]["link"]
    
    out_path = dest_dir / f"pexels_broll_{video['id']}.mp4"
    v_resp = requests.get(best_file, timeout=60)
    v_resp.raise_for_status()
    out_path.write_bytes(v_resp.content)
    return str(out_path)