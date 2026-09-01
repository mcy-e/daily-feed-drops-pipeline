import logging
import os
import pathlib
import random
import traceback
import subprocess

from scripts.constants import TEMP_DIR
from scripts.generators.broll_fetcher import fetch_broll
from scripts.generators.cursed_fetcher import fetch_cursed_items
from scripts.pipelines.schedule import is_scheduled_time, load_manager_config
from scripts.render.cursed_assemble import render_cursed_clip
from scripts.notifications.telegram import send_message, send_video

logger = logging.getLogger(__name__)

CONTENT_TYPE = "cursed_screenshots"


def run_cursed_pipeline(force: bool = False):
    logger.info("=" * 50)
    logger.info("Pipeline START: cursed_screenshots (force=%s)", force)
    logger.info("=" * 50)

    config = load_manager_config()
    normalized = config if "schedules" in config else {}
    manual_mode = normalized.get("manual_mode", {}).get(CONTENT_TYPE, True)
    privacy_status = normalized.get("privacy_status", {}).get(CONTENT_TYPE, "public")
    schedules = normalized.get("schedules", {}).get(CONTENT_TYPE, [])

    if not force:
        if not is_scheduled_time(schedules):
            logger.info("Not scheduled to run now — skipping cursed_screenshots")
            return

    run_dir = TEMP_DIR / CONTENT_TYPE
    run_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        logger.info("Stage 1: Fetching Cursed Items")
        items = fetch_cursed_items()
        if not items:
            logger.error("No cursed items fetched — aborting")
            send_message("Pipeline aborted: failed to fetch cursed items.")
            return

        logger.info("Stage 2: Rendering Clips")
        clip_paths = []
        for i, item in enumerate(items):
            logger.info("Rendering clip %d/%d", i + 1, len(items))
            # 40 seconds of b-roll is usually enough for a cursed clip
            broll_path = fetch_broll(run_dir / "broll", 40.0)
            clip_path = render_cursed_clip(item, run_dir / "clips", bg_video_path=broll_path)
            if clip_path:
                clip_paths.append(clip_path)

        if not clip_paths:
            logger.error("No clips were rendered successfully — aborting")
            return

        logger.info("Stage 3: Concatenating Compilation")
        concat_txt = run_dir / "concat_final.txt"
        with open(concat_txt, "w") as f:
            for p in clip_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")

        final_video = str(run_dir / "final_cursed_compilation.mp4")
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-t", "420",  # max 7 minutes
            "-c", "copy",
            final_video
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        logger.info("Stage 4: Telegram + YouTube Delivery")
        vol = random.randint(1, 999)
        title = f"Cursed Screenshots That Will Haunt You (Vol. {vol}) #Shorts"
        description = "A collection of the most cursed and funny screenshots from the internet.\n\nLike and Subscribe for more suffering.\n\n#cursed #funny #screenshots #comedy #compilation"

        if not manual_mode:
            logger.info("Uploading to YouTube...")
            try:
                from scripts.upload.youtube_upload import upload_video
                youtube_url = upload_video(
                    video_path=final_video,
                    title=title[:80],
                    description=description,
                    tags=["cursed", "funny", "screenshots", "comedy", "compilation"],
                    category_id="23",
                    privacy_status=privacy_status,
                )
                logger.info("Stage 5: Telegram — sending YouTube link")
                send_message(
                    f"Video uploaded!\n\nTitle: {title}\n\nLink: {youtube_url}\n\nDescription:\n{description}"
                )
            except Exception as exc:
                logger.error("YouTube upload failed: %s", exc)
                send_message(f"YouTube upload FAILED. Sending video for manual upload.\n\nTitle: {title}\n\nDescription:\n{description}")
                send_video(final_video, description)
        else:
            logger.info("Telegram Delivery (manual mode)")
            send_video(final_video, description)

        logger.info("Pipeline COMPLETE!")

    except Exception as exc:
        logger.error("Pipeline CRASHED: %s\n%s", exc, traceback.format_exc())
        try:
            send_message(f"Cursed Pipeline CRASHED: {exc}")
        except Exception:
            pass
        raise
