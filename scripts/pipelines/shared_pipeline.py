import logging
import pathlib
import random
import traceback

from scripts.constants import TEMP_DIR
from scripts.generators.broll_fetcher import fetch_broll
from scripts.generators.meme_fetcher import delete_custom_meme_from_drive, fetch_meme
from scripts.pipelines.schedule import is_scheduled_time, load_manager_config
from scripts.render.assemble import composite_meme
from scripts.notifications.telegram import send_message, send_video
from scripts.utils.metadata_generator import generate_youtube_metadata

logger = logging.getLogger(__name__)

CONTENT_TYPES = ("meme_recap", "cursed_screenshots")

def run_content_pipeline(content_type: str, force: bool = False):
    logger.info("=" * 50)
    logger.info(f"Pipeline START: {content_type} (force={force})")
    logger.info("=" * 50)

    if content_type not in CONTENT_TYPES:
        logger.error(f"Unknown content type: {content_type}")
        return

    config = load_manager_config()
    normalized = config if "schedules" in config else {}
    manual_mode = normalized.get("manual_mode", {}).get(content_type, True)
    privacy_status = normalized.get("privacy_status", {}).get(content_type, "private")
    schedules = normalized.get("schedules", {}).get(content_type, [])

    if not force:
        if not is_scheduled_time(schedules):
            logger.info(f"Not scheduled to run now — skipping {content_type}")
            return

    run_dir = TEMP_DIR / content_type
    run_dir.mkdir(parents=True, exist_ok=True)
    
    meme = None
    try:
        # 1. Fetch Meme Image
        logger.info("Stage 1: Fetching Meme")
        meme = fetch_meme(run_dir / "memes")
        if not meme or not meme.get("image_path"):
            logger.error("No meme fetched — aborting")
            send_message("Pipeline aborted: failed to fetch a meme.")
            return

        # 2. Determine Duration
        title = meme.get("title", "")
        calculated_duration = 4.0 + (len(title) / 10.0)
        duration = max(6.0, min(14.0, calculated_duration))
        logger.info(f"Meme duration set to {duration:.1f}s (based on title length {len(title)})")

        # 3. Fetch B-Roll
        logger.info("Stage 2: Fetching B-Roll")
        broll_path = fetch_broll(run_dir / "broll", duration)
        if not broll_path:
            logger.error("No B-Roll fetched — aborting")
            send_message("Pipeline aborted: failed to fetch B-Roll.")
            return

        # 4. Assemble
        logger.info("Stage 3: Compositing Video")
        final_video = composite_meme(meme["image_path"], broll_path, run_dir / "output")

        # 5. Telegram + YouTube
        title = meme["title"]
        meta = generate_youtube_metadata(title, meme.get("image_path"))
        hashtag_str = " ".join(meta["hashtags"])
        description = f"{meta['description']}\n\n{hashtag_str}"

        if not manual_mode:
            logger.info("Stage 5: YouTube Upload")
            try:
                from scripts.upload.youtube_upload import upload_video
                youtube_url = upload_video(
                    video_path=final_video,
                    title=title[:80],
                    description=description,
                    tags=["meme", "funny", "viral", "shorts", "gaming"],
                    privacy_status=privacy_status,
                )
                logger.info("Stage 5b: Telegram — sending YouTube link")
                send_message(
                    f"Video uploaded!\n\n"
                    f"Title: {title}\n\n"
                    f"Link: {youtube_url}\n\n"
                    f"Description:\n{description}"
                )
            except Exception as exc:
                logger.error("YouTube upload failed: %s", exc)
                send_message(f"YouTube upload FAILED. Sending video for manual upload.\n\nTitle: {title}\n\nDescription:\n{description}")
                send_video(final_video, description)
        else:
            logger.info("Stage 4: Telegram Delivery (manual mode)")
            send_video(final_video, description)

        # 7. Cleanup
        logger.info("Stage 6: Cleanup Custom Memes")
        delete_custom_meme_from_drive(meme)
        
        logger.info("Pipeline COMPLETE!")

    except Exception as exc:
        logger.error(f"Pipeline CRASHED: {exc}\n{traceback.format_exc()}")
        try:
            send_message(f"Pipeline CRASHED: {exc}")
        except:
            pass
        raise