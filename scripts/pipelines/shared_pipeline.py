import json
import logging
import pathlib
import shutil
import uuid

from scripts.constants import (
    CONTENT_TYPES,
    DEFAULT_TEMP_DIR,
    YOUTUBE_TAGS_BY_CONTENT_TYPE,
)
from scripts.generators.content_gen import generate_script
from scripts.generators.broll_fetcher import fetch_aesthetic_broll
from scripts.generators.image_fetcher import fetch_pexels_image
from scripts.generators.meme_fetcher import fetch_meme_script
from scripts.manim_scenes.scene_builder import render_all_segments
from scripts.notifications.telegram import send_message, send_video
from scripts.pipelines.schedule import load_manager_config, should_run_for_schedule
from scripts.render.assemble import assemble_video
from scripts.render.segment_audio import generate_all_segment_audio

logger = logging.getLogger(__name__)


def _cleanup_root_temp() -> None:
    """Delete and recreate the root temp directory at pipeline start."""
    if DEFAULT_TEMP_DIR.exists():
        shutil.rmtree(DEFAULT_TEMP_DIR)
    DEFAULT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Cleaned temp directory: %s", DEFAULT_TEMP_DIR)


def _cleanup_temp_dir(run_dir: pathlib.Path) -> None:
    """Delete and recreate the run's temp output directory."""
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Temp directory ready: %s", run_dir)


def _fetch_segment_images(script: dict, images_dir: pathlib.Path) -> None:
    """Download Pexels images for segments that need them."""
    for segment in script["segments"]:
        if segment.get("image_needed") and segment.get("image_query"):
            query = segment["image_query"]
            image_path = fetch_pexels_image(query, images_dir)
            segment["image_path"] = image_path
            segment["visual_type"] = "image"


def _get_content_config(config: dict, content_type: str) -> dict:
    """Extract per-content-type settings from manager config."""
    return {
        "manual_mode": config.get("manual_mode", {}).get(content_type, False),
        "privacy_status": config.get("privacy_status", {}).get(content_type, "private"),
        "schedules": config.get("schedules", {}).get(content_type, []),
    }


def run_content_pipeline(content_type: str, force: bool = False) -> None:
    """Orchestrate the full shared content pipeline for one content type."""
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"Unknown content type: {content_type}. Valid: {CONTENT_TYPES}")

    config = load_manager_config()
    type_config = _get_content_config(config, content_type)

    if not should_run_for_schedule(content_type, config=config, force=force):
        return

    _cleanup_root_temp()

    run_id = uuid.uuid4().hex[:8]
    run_dir = DEFAULT_TEMP_DIR / content_type / run_id
    _cleanup_temp_dir(run_dir)

    images_dir = run_dir / "images"
    audio_dir = run_dir / "audio"
    manim_dir = run_dir / "manim"
    segments_dir = run_dir / "segments"
    for d in (images_dir, audio_dir, manim_dir, segments_dir):
        d.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Generate script
        if content_type == "meme_recap":
            script = fetch_meme_script(images_dir, force=force)
        else:
            script = generate_script(content_type)

        script_path = run_dir / "script.json"
        script_path.write_text(json.dumps(script, indent=2), encoding="utf-8")
        logger.info("Script saved: %s", script_path)

        # 2. Fetch images for image_needed segments
        _fetch_segment_images(script, images_dir)

        # 3. Generate TTS per segment
        segments_audio = generate_all_segment_audio(script["segments"], str(audio_dir))

        # 4. Render Manim scenes (transparent overlay)
        segment_videos = render_all_segments(
            script["segments"], content_type, segments_audio, manim_dir
        )

        # 5. Fetch satisfying B-Roll background
        broll_path = None
        try:
            broll_path = fetch_aesthetic_broll(run_dir / "broll")
            logger.info("B-Roll fetched: %s", broll_path)
        except Exception as broll_exc:
            logger.warning("B-Roll fetch failed (%s) — falling back to blur-pad", broll_exc)

        # 6. Composite Manim onto B-Roll per segment, then concatenate
        final_path = assemble_video(
            segment_videos, segments_audio, segments_dir, broll_path=broll_path
        )

        # 7. Delivery
        title = script["title"]
        description = f"{title}\n\n#shorts #{content_type.replace('_', '')}"
        tags = YOUTUBE_TAGS_BY_CONTENT_TYPE.get(content_type, ["shorts"])
        manual_mode = type_config["manual_mode"]
        privacy_status = type_config["privacy_status"]

        if manual_mode:
            logger.info("Manual mode ON for %s — sending video to Telegram.", content_type)
            caption = f"🎬 <b>{content_type.replace('_', ' ').title()}</b>\n\n{title}"
            send_video(final_path, caption)
        else:
            from scripts.upload.youtube_upload import upload_video

            logger.info("Manual mode OFF for %s — uploading to YouTube.", content_type)
            url = upload_video(
                final_path, title, description,
                privacy_status=privacy_status,
                tags=tags,
            )
            msg = (
                f"✅ <b>Pipeline Success</b>\n\n"
                f"Type: {content_type}\n"
                f"Title: {title}\n"
                f"Link: {url}"
            )
            send_message(msg)

        logger.info("Content pipeline complete for %s.", content_type)

    except Exception as exc:
        logger.error("Content pipeline failed for %s: %s", content_type, exc)
        send_message(
            f"❌ <b>Pipeline Failed</b>\n\n"
            f"Type: {content_type}\n"
            f"Error: <code>{exc}</code>"
        )
        raise
