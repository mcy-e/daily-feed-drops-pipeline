import json
import logging
import pathlib
import random
import shutil
import uuid
import requests

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

END_CARD_HOOKS = {
    "dark_facts": ["Did you know this? Comment below 👇", "Follow for more dark facts", "Share this if it shocked you"],
    "would_you_rather": ["Comment A or B 👇", "Tag someone who would pick the wrong one", "Which would YOU choose?"],
    "football_trivia": ["Did you get it right? Comment below", "Follow for daily football facts", "Share with a football fan!"],
    "viral_news": ["What do you think about this? Comment below", "Follow for more", "Share this story!"],
    "explained_topic": ["Did you know this? Follow for more", "Share this with someone who needs to know", "Drop a comment if this surprised you!"],
    "quiz_riddle": ["Comment your answer below!", "How fast did you get it?", "Tag a friend to solve this!"],
    "meme_recap": ["Follow for daily memes", "Tag someone in this", "Double tap if you laughed 😂"],
}


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


def _derive_image_query(segment: dict, content_type: str) -> str:
    """Derive a Pexels search query from segment data or narration as a fallback."""
    if segment.get("image_query"):
        return segment["image_query"]
    # Extract the first meaningful words from the narration as a fallback query
    narration = segment.get("narration", "")
    words = [w for w in narration.split() if len(w) > 3][:5]
    return " ".join(words) if words else content_type.replace("_", " ")


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

        # 2. Inject engagement end-card segment
        hooks = END_CARD_HOOKS.get(content_type, ["Follow for more!"])
        end_text = random.choice(hooks)
        end_seg_id = max(s["id"] for s in script["segments"]) + 1
        script["segments"].append({
            "id": end_seg_id,
            "narration": end_text,
            "visual_type": "text",
            "visual_content": end_text,
            "image_needed": False,
            "image_query": content_type.replace("_", " ") + " social media",
            "image_path": "",
            "pause_after": 0.5,
        })

        # 3. Fetch a real Pexels image for every segment
        news_image_url = script.get("news_image_url")
        if news_image_url and script["segments"]:
            logger.info("Downloading GNews image for foreground overlay: %s", news_image_url)
            try:
                img_path = images_dir / "news_img.jpg"
                resp = requests.get(news_image_url, timeout=30, verify=False)
                resp.raise_for_status()
                with open(img_path, "wb") as f:
                    f.write(resp.content)
                script["segments"][0]["visual_type"] = "image"
                script["segments"][0]["image_path"] = str(img_path)
            except Exception as e:
                logger.warning("Failed to download news image: %s", e)

        _fetch_all_segment_images(script, content_type, images_dir)


        # 3. Generate TTS per segment (skipped automatically for non-voice types)
        segments_audio = generate_all_segment_audio(
            script["segments"], str(audio_dir), content_type=content_type
        )

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
