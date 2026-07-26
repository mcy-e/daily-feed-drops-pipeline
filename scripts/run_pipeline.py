import json
import logging
import os
import pathlib
import random
from dotenv import load_dotenv

from scripts.constants import DRIVE_FOLDERS_CONFIG_PATH, DEFAULT_OUTPUT_DIR
from scripts.db.clip_tracker import get_used_clip_ids, mark_clip_used
from scripts.generators.football import (
    get_service, pick_weighted_subfolder, download_file, find_companion_json,
)
from scripts.render.trim import smart_trim_analysis, simple_trim_analysis, curated_trim_analysis
from scripts.render.render import render_video
from scripts.upload.youtube_upload import upload_video
from scripts.notifications.telegram import send_message

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

def main():
    try:
        logger.info("Starting automated football pipeline run")
        
        # 1. Drive Connection & File Selection
        with open(DRIVE_FOLDERS_CONFIG_PATH, "r") as f:
            folders = json.load(f)
            
        folder_config = folders.get("football")
        if not folder_config or not isinstance(folder_config, dict):
            raise ValueError("Football folder config missing or invalid in config")
            
        service = get_service()
        file_meta = pick_weighted_subfolder(service, folder_config)
        local_path = download_file(service, file_meta)
        
        video_id = file_meta["id"]
        content_mode = file_meta.get("content_mode", "highlight")
        
        # 2. Curated-clip check (companion JSON on Drive)
        folder_id = file_meta.get("_folder_id")
        companion_path = None
        if folder_id:
            companion_path = find_companion_json(
                service, folder_id, file_meta["name"]
            )
        
        curated_clip = None
        if companion_path:
            curated_clip = _pick_unused_clip(companion_path, video_id)
        
        # 3. Trimming & Captions — branched by curated vs auto
        if curated_clip:
            start_time = curated_clip["start"]
            end_time = curated_clip["end"]
            mark_clip_used(video_id, curated_clip["id"])
            logger.info("Using curated clip '%s': %.2fs -> %.2fs", curated_clip["id"], start_time, end_time)
            
            start_time, end_time, srt_path = curated_trim_analysis(
                local_path, DEFAULT_OUTPUT_DIR, start_time, end_time
            )
        elif content_mode == "highlight":
            start_time, end_time, srt_path = smart_trim_analysis(local_path, DEFAULT_OUTPUT_DIR)
        else:
            start_time, end_time, srt_path = simple_trim_analysis(local_path)
        
        # 4. Render (Pad, Blur, and conditionally Burn Subtitles)
        output_path = render_video(local_path, DEFAULT_OUTPUT_DIR, start_time, end_time, srt_path)
        
        # 5. Upload to YouTube
        title = f"Daily Football Highlight! ⚽🔥 #shorts #football"
        description = "Check out this amazing football moment! Subscribe for daily highlights."
        url = upload_video(output_path, title, description)
        
        # 6. Notify Success
        msg = f"✅ <b>Pipeline Success</b>\n\nVideo uploaded: {url}\nFile: {file_meta['name']}"
        send_message(msg)
        logger.info("Pipeline run complete.")
        
    except Exception as exc:
        logger.error("Pipeline run failed: %s", exc)
        msg = f"❌ <b>Pipeline Failed</b>\n\nError: <code>{exc}</code>"
        send_message(msg)
        raise


def _pick_unused_clip(companion_path: str, video_id: str) -> dict | None:
    """Load the companion JSON, exclude already-used clips, pick one at random."""
    try:
        with open(companion_path, "r") as f:
            data = json.load(f)
        
        clips = data.get("clips", [])
        if not clips:
            logger.info("Companion JSON has no clips array")
            return None
        
        used_ids = get_used_clip_ids(video_id)
        available = [c for c in clips if c.get("id") not in used_ids]
        
        if not available:
            logger.info("All %d clips already used for video %s, falling back to auto-detection", len(clips), video_id)
            return None
        
        chosen = random.choice(available)
        logger.info("Selected curated clip '%s' (%d available, %d used)", chosen["id"], len(available), len(used_ids))
        return chosen
        
    except Exception as exc:
        logger.warning("Failed to parse companion JSON: %s. Falling back to auto-detection.", exc)
        return None


if __name__ == "__main__":
    main()
