import json
import logging
import pathlib
import random

from scripts.constants import CHANNELS, CONTENT_TYPES, TEMP_DIR, MANAGER_CONFIG_PATH
from scripts.generators.broll_fetcher import fetch_aesthetic_broll
from scripts.generators.content_gen import generate_script
from scripts.generators.pexels_fetcher import fetch_pexels_image
from scripts.pipelines.schedule import is_scheduled_time, load_manager_config
from scripts.render.assemble import assemble_video
from scripts.render.segment_audio import generate_all_audio
from scripts.manim_scenes.scene_builder import render_all_segments
from scripts.uploaders.telegram_bot import send_to_telegram
from scripts.uploaders.youtube_uploader import upload_video

logger = logging.getLogger(__name__)

END_CARD_HOOKS = {
    "dark_facts": ["Did you know this? Comment below!", "Hit subscribe if this gave you chills."],
    "would_you_rather": ["Comment A or B!", "What would you choose? Let us know!"],
    "football_trivia": ["Did you guess it? Subscribe for more!", "Drop a like if you love football!"],
    "viral_news": ["What do you think? Comment below!", "Follow for daily news drops!"],
    "explained_topic": ["Did you learn something? Like & Subscribe!", "Follow for daily explainers!"],
    "meme_recap": ["Send this to a friend!", "Follow for daily memes!"],
    "quiz_riddle": ["Did you get it right? Comment below!", "Subscribe for more riddles!"],
    "motivation_content": ["Save this for later!", "Follow to stay motivated!"],
    "kids_content": ["Like and subscribe for more fun!", "Share with your friends!"],
}


def _derive_image_query(segment: dict, content_type: str) -> str:
    """Generate a decent stock photo query based on the segment text."""
    # We strip common stop words and grab the most "noun-like" phrase if possible
    # For now, a naive fallback: just use the first few words of visual_content
    base_text = segment.get("visual_content") or segment.get("narration", "")
    words = [w for w in base_text.split() if len(w) > 3]
    query = " ".join(words[:3])
    
    # Overrides based on content type to ensure relevant imagery
    if content_type == "dark_facts":
        query = "creepy dark mystery " + query
    elif content_type == "viral_news":
        query = "news reporter " + query
    elif content_type == "football_trivia":
        query = "football soccer stadium " + query
        
    return query


def _fetch_all_segment_images(script: dict, content_type: str, images_dir: pathlib.Path) -> None:
    """Download a real Pexels image for the first segment and re-use it for all subsequent segments.
    This creates a single static image holding position over the B-Roll for the whole video."""
    first_image_path = None
    for segment in script["segments"]:
        # Skip segments that already have an image (e.g. meme images or news images)
        if segment.get("image_path") and pathlib.Path(segment["image_path"]).exists():
            segment["visual_type"] = "image"
            if not first_image_path:
                first_image_path = segment["image_path"]
            continue

        if first_image_path:
            # Re-use the same image to keep the background static while text updates
            segment["image_path"] = first_image_path
            segment["visual_type"] = "image"
            continue

        query = _derive_image_query(segment, content_type)
        try:
            image_path = fetch_pexels_image(query, images_dir)
            segment["image_path"] = image_path
            segment["visual_type"] = "image"
            first_image_path = image_path
            logger.info("Fetched static image for video: query='%s'", query)
        except Exception as exc:
            logger.warning("Could not fetch image for segment %d ('%s'): %s — keeping text card", segment["id"], query, exc)


def _get_content_config(config: dict, content_type: str) -> dict:
    """Extract per-content-type settings from manager config."""
    return {
        "manual_mode": config.get("manual_mode", {}).get(content_type, True),
        "privacy_status": config.get("privacy_status", {}).get(content_type, "private"),
        "schedules": config.get("schedules", {}).get(content_type, []),
    }


def run_content_pipeline(content_type: str, force: bool = False):
    """
    Main orchestration function for generating and rendering content.
    """
    logger.info("==================================================")
    logger.info("Starting pipeline for content type: %s", content_type)
    logger.info("==================================================")

    config = load_manager_config()

    # 1. Check schedule unless forced
    if not force:
        type_config = _get_content_config(config, content_type)
        schedules = type_config["schedules"]
        should_run = False
        for s in schedules:
            if is_scheduled_time(s):
                should_run = True
                break
                
        if not should_run:
            logger.info("Skipping %s — not scheduled to run now.", content_type)
            return

    # Setup directories
    run_dir = TEMP_DIR / content_type
    run_dir.mkdir(parents=True, exist_ok=True)

    images_dir = run_dir / "images"
    audio_dir = run_dir / "audio"
    video_dir = run_dir / "video"

    try:
        # 1. Generate Script
        logger.info("Stage 1: Generating Script")
        if content_type == "meme_recap":
            from scripts.generators.meme_gen import get_latest_memes
            memes = get_latest_memes()
            if not memes:
                logger.warning("No memes found. Aborting.")
                return
            # Use only one meme for a 7-second short as requested
            meme = random.choice(memes)
            script = {
                "title": "Meme Recap",
                "description": "Daily meme drop!",
                "tags": ["memes", "funny"],
                "segments": [
                    {
                        "id": 1,
                        "narration": meme.get("title", "Funny meme"),
                        "visual_type": "image",
                        "visual_content": meme.get("title", ""),
                        "image_path": meme["image_path"],
                        "image_needed": True
                    }
                ]
            }
        else:
            script = generate_script(content_type)

        script_path = run_dir / "script.json"
        script_path.write_text(json.dumps(script, indent=2), encoding="utf-8")
        logger.info("Script saved: %s", script_path)

        # 3. Fetch specific images if needed
        logger.info("Stage 3: Fetching specific segment imagery")
        _fetch_all_segment_images(script, content_type, images_dir)

        # 4. Generate TTS & Audio
        logger.info("Stage 4: Generating Audio")
        segments_audio = generate_all_audio(script["segments"], content_type, audio_dir)

        # 5. Render individual video segments (Manim/PIL)
        logger.info("Stage 5: Rendering Video Segments")
        segment_videos = render_all_segments(script["segments"], content_type, segments_audio, video_dir)

        # 6. Fetch B-Roll
        logger.info("Stage 6: Fetching B-Roll")
        broll_dir = run_dir / "broll"
        broll_path = fetch_aesthetic_broll(broll_dir)

        # 7. Assemble final video
        logger.info("Stage 7: Assembling Final Output")
        final_video = assemble_video(broll_path, segment_videos, segments_audio, run_dir)
        
        # 8. Upload based on Manual Mode
        type_config = _get_content_config(config, content_type)
        manual_mode = type_config["manual_mode"]
        
        if manual_mode:
            logger.info("Manual mode ON for %s — sending video to Telegram.", content_type)
            send_to_telegram(final_video, f"[{content_type}] Ready for review")
        else:
            logger.info("Automatic mode ON for %s — uploading to YouTube.", content_type)
            privacy = type_config["privacy_status"]
            upload_video(
                video_path=final_video,
                title=script["title"],
                description=script["description"],
                tags=script["tags"],
                privacy_status=privacy
            )
            
            # Send notification to Telegram
            send_to_telegram(final_video, f"[{content_type}] Uploaded to YouTube ({privacy})")

    except Exception as e:
        logger.error("Pipeline failed for %s: %s", content_type, e, exc_info=True)
        raise
