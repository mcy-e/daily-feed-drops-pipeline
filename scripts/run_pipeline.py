import json
import logging
import os
import pathlib
import random
import datetime
import argparse
from dotenv import load_dotenv

from scripts.constants import PROJECT_ROOT, DEFAULT_OUTPUT_DIR
from scripts.generators.football import generate_football_content
from scripts.render.trim import simple_trim_analysis
from scripts.render.render import render_video
from scripts.upload.youtube_upload import upload_video
from scripts.notifications.telegram import send_message, send_video

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

def _is_scheduled_time(scheduled_times: list[str], tolerance_minutes: int = 15) -> bool:
    """Check if the current time matches any scheduled time within the tolerance."""
    now = datetime.datetime.now()
    current_minutes = now.hour * 60 + now.minute
    
    for t in scheduled_times:
        try:
            h, m = map(int, t.split(":"))
            sched_minutes = h * 60 + m
            diff = abs(current_minutes - sched_minutes)
            
            if diff <= tolerance_minutes or diff >= (24 * 60 - tolerance_minutes):
                return True
        except ValueError:
            logger.warning("Invalid time format in schedule: %s", t)
            
    return False

def main():
    parser = argparse.ArgumentParser(description="Run the daily feed drops pipeline.")
    parser.add_argument("--force", action="store_true", help="Bypass the schedule time check and run immediately.")
    args = parser.parse_args()
    
    force_run = args.force or os.getenv("FORCE_RUN", "").lower() == "true"

    try:
        logger.info("Starting automated football pipeline run")
        
        # 1. Load config and check schedule
        config_path = PROJECT_ROOT / "config" / "manager_config.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)
        else:
            logger.warning("No manager_config.json found. Proceeding with defaults.")
            config = {"manual_mode": False, "schedules": {}}
            
        manual_mode = config.get("manual_mode", False)
        football_schedules = config.get("schedules", {}).get("football", [])
        
        if football_schedules:
            if force_run:
                logger.info("Force run enabled. Bypassing schedule check for football.")
            elif not _is_scheduled_time(football_schedules):
                logger.info("Current time does not match any scheduled slots for football. Skipping execution.")
                return
        else:
            logger.info("No schedule configured for football. Running immediately.")
            
        # 2. Generate AI content
        local_path = generate_football_content()
        
        # 3. Trimming & Captions
        start_time, end_time, srt_path, audio_path = simple_trim_analysis(local_path)
        
        # 4. Render (Pad, Blur, and conditionally Burn Subtitles)
        output_path = render_video(local_path, DEFAULT_OUTPUT_DIR, start_time, end_time, srt_path, audio_path)
        
        # 5. Delivery based on manual_mode
        title = "Daily Football Highlight! ⚽🔥 #shorts #football"
        description = "Check out this amazing football moment! Subscribe for daily highlights."
        
        if manual_mode:
            logger.info("Manual mode is ON. Sending video to Telegram directly.")
            msg = f"⚽ <b>Manual Mode: Football Content</b>\n\nTitle: {title}"
            send_video(output_path, msg)
        else:
            logger.info("Manual mode is OFF. Uploading to YouTube.")
            url = upload_video(output_path, title, description)
            msg = f"✅ <b>Pipeline Success</b>\n\nVideo uploaded: {url}\nType: Football\nTitle: {title}"
            send_message(msg)
            
        logger.info("Pipeline run complete.")
        
    except Exception as exc:
        logger.error("Pipeline run failed: %s", exc)
        msg = f"❌ <b>Pipeline Failed</b>\n\nError: <code>{exc}</code>"
        send_message(msg)
        raise

if __name__ == "__main__":
    main()
