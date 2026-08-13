import json
import logging
import os
import pathlib
import random
import subprocess
import uuid

from scripts.constants import TEMP_DIR, MANAGER_CONFIG_PATH
from scripts.generators.broll_fetcher import fetch_aesthetic_broll
from scripts.generators.meme_fetcher import fetch_meme_script_simple
from scripts.generators.reddit_fetcher import fetch_reddit_script
from scripts.generators.image_fetcher import fetch_pexels_image
from scripts.pipelines.schedule import load_manager_config, is_scheduled_time
from scripts.render.assemble import assemble_video
from scripts.render.image_card_renderer import render_image_card
from scripts.notifications.telegram import send_video as telegram_send_video, send_message as telegram_send_message

logger = logging.getLogger(__name__)

CONTENT_TYPES = ("meme_recap", "dark_facts", "shower_thoughts")

# Sound config: 70% night atmosphere, 30% owl or cockroach
SOUND_WEIGHTS = {"night": 0.70, "owl": 0.15, "cockroach": 0.15}


def _pick_ambient_sound(output_dir: pathlib.Path) -> str:
    """Generate ambient audio. 70% night atmosphere, 15% owl, 15% cockroach (via ffmpeg filters)."""
    choice = random.random()
    out = str(output_dir / "ambient.aac")
    output_dir.mkdir(parents=True, exist_ok=True)

    if choice < 0.70:
        # Night atmosphere: mix brown + pink noise at low volume
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=c=brown:r=44100:a=0.08",
            "-i", "anoisesrc=c=pink:r=44100:a=0.04",
            "-filter_complex", "amix=inputs=2:duration=first",
            "-t", "90", "-c:a", "aac", out,
        ]
        label = "night"
    elif choice < 0.85:
        # Owl: narrow band filtered noise at ~800Hz
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=c=white:r=44100:a=0.05",
            "-af", "bandpass=f=800:width_type=h:w=200,volume=0.3",
            "-t", "90", "-c:a", "aac", out,
        ]
        label = "owl"
    else:
        # Cockroach/insect: higher freq noise
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=c=white:r=44100:a=0.04",
            "-af", "bandpass=f=3000:width_type=h:w=500,volume=0.25",
            "-t", "90", "-c:a", "aac", out,
        ]
        label = "cockroach"

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info("Ambient sound generated: %s", label)
        return out
    except Exception as exc:
        logger.warning("Ambient generation failed (%s): %s", label, exc)
        return None


def _download_image(url: str, dest: pathlib.Path) -> str | None:
    """Download an image from a URL and save it to dest."""
    import requests, urllib3
    urllib3.disable_warnings()
    try:
        resp = requests.get(url, timeout=15, verify=False)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return str(dest)
    except Exception as exc:
        logger.warning("Image download failed from %s: %s", url, exc)
        return None


def _get_or_fetch_image(segment: dict, images_dir: pathlib.Path, content_type: str) -> str | None:
    """Return a local image path for the segment, downloading or fetching from Pexels if needed."""
    images_dir.mkdir(parents=True, exist_ok=True)

    # Already downloaded
    existing = segment.get("image_path", "")
    if existing and pathlib.Path(existing).exists():
        return existing

    # Reddit posts may provide a direct image URL
    reddit_url = segment.get("reddit_image_url")
    if reddit_url:
        dest = images_dir / f"reddit_{hash(reddit_url) % 99999}.jpg"
        path = _download_image(reddit_url, dest)
        if path:
            return path

    # Fallback: Pexels search
    query_text = segment.get("visual_content") or segment.get("narration", "")
    words = [w for w in query_text.split() if len(w) > 3]
    query = " ".join(words[:4])
    if content_type == "dark_facts":
        query = "dark mystery " + query
    elif content_type == "shower_thoughts":
        query = "thought philosophy " + query

    try:
        path = fetch_pexels_image(query, images_dir)
        if path:
            return path
    except Exception as exc:
        logger.warning("Pexels fallback failed for '%s': %s", query, exc)
    
    # Ultimate fallback: generate a beautiful gradient or solid color image
    fallback_path = images_dir / f"fallback_{uuid.uuid4().hex[:6]}.jpg"
    try:
        from PIL import Image
        img = Image.new('RGB', (1080, 1920), color=(random.randint(20,50), random.randint(20,50), random.randint(20,50)))
        img.save(fallback_path)
        return str(fallback_path)
    except Exception as exc:
        logger.error("Failed to create fallback image: %s", exc)
        return None


def _render_card_to_video(image_path: str, text: str, content_type: str,
                          duration: float, output_dir: pathlib.Path) -> str:
    """Render the meme card image and convert it to a silent video segment."""
    output_dir.mkdir(parents=True, exist_ok=True)
    card_path = str(output_dir / "card.png")
    video_path = str(output_dir / "segment.mov")

    render_image_card(image_path, text, content_type, card_path)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", card_path,
        "-t", str(duration),
        "-c:v", "qtrle",
        video_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return video_path


def _reading_duration(text: str, wps: float = 2.2, minimum: float = 20.0) -> float:
    return max(minimum, len(text.split()) / wps)



def _get_content_config(config: dict, content_type: str) -> dict:
    normalized = config if "schedules" in config else {}
    return {
        "manual_mode": normalized.get("manual_mode", {}).get(content_type, True),
        "privacy_status": normalized.get("privacy_status", {}).get(content_type, "private"),
        "schedules": normalized.get("schedules", {}).get(content_type, []),
    }


def run_content_pipeline(content_type: str, force: bool = False):
    logger.info("=" * 50)
    logger.info("Pipeline START: %s (force=%s)", content_type, force)
    logger.info("=" * 50)

    if content_type not in CONTENT_TYPES:
        logger.error("Unknown content type: %s. Valid: %s", content_type, CONTENT_TYPES)
        return

    config = load_manager_config()

    if not force:
        type_cfg = _get_content_config(config, content_type)
        schedules = type_cfg["schedules"]
        if not is_scheduled_time(schedules):
            logger.info("Not scheduled to run now — skipping %s", content_type)
            return

    run_dir = TEMP_DIR / content_type
    run_dir.mkdir(parents=True, exist_ok=True)
    images_dir = run_dir / "images"
    seg_dir = run_dir / "segment"

    try:
        # ── 1. Fetch content ──────────────────────────────────────────────
        logger.info("Stage 1: Fetching content")
        if content_type == "meme_recap":
            script = fetch_meme_script_simple()
        else:
            script = fetch_reddit_script(content_type)

        if not script or not script.get("segments"):
            logger.error("No content fetched for %s — aborting", content_type)
            telegram_send_message(f"[{content_type}] Pipeline aborted: no content fetched.")
            return

        (run_dir / "script.json").write_text(
            json.dumps(script, indent=2), encoding="utf-8"
        )
        segment = script["segments"][0]
        text = segment.get("visual_content") or segment.get("narration", "")
        logger.info("Content fetched: %s", text[:80])

        # ── 2. Fetch image ────────────────────────────────────────────────
        logger.info("Stage 2: Fetching image")
        image_path = _get_or_fetch_image(segment, images_dir, content_type)
        if not image_path:
            logger.error("No image available — aborting")
            telegram_send_message(f"[{content_type}] Pipeline aborted: image fetch failed.")
            return
        segment["image_path"] = image_path

        # ── 3. Calculate duration ─────────────────────────────────────────
        duration = _reading_duration(text)
        logger.info("Video duration: %.1fs", duration)

        # ── 4. Render card to video ────────────────────────────────────────
        logger.info("Stage 4: Rendering meme card")
        segment_video = _render_card_to_video(image_path, text, content_type, duration, seg_dir)

        # ── 5. Fetch B-Roll ────────────────────────────────────────────────
        logger.info("Stage 5: Fetching B-Roll")
        broll_path = fetch_aesthetic_broll(run_dir / "broll")

        # ── 6. Build ambient audio ─────────────────────────────────────────
        logger.info("Stage 6: Generating ambient audio")
        ambient_path = _pick_ambient_sound(run_dir / "audio")

        # ── 7. Assemble ────────────────────────────────────────────────────
        logger.info("Stage 7: Assembling final video")

        # Build a minimal audio_meta that assemble_video expects
        audio_meta = {
            "id": 1,
            "audio_path": str(run_dir / "audio" / "silent.aac"),
            "narration": text,
            "duration": 0.0,
            "pause_after": 0.0,
            "total_duration": duration,
            "segment_duration": duration,
        }
        # Create silent stub audio so assemble_video doesn't fail
        (run_dir / "audio").mkdir(parents=True, exist_ok=True)
        silent_cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration), "-c:a", "aac",
            audio_meta["audio_path"],
        ]
        subprocess.run(silent_cmd, capture_output=True, check=True)

        final_video = assemble_video(
            segment_videos=[segment_video],
            segment_audios=[audio_meta],
            output_dir=run_dir / "output",
            broll_path=broll_path,
        )

        # Overlay ambient if we have it
        if ambient_path and pathlib.Path(ambient_path).exists():
            dubbed_path = str(run_dir / "output" / "final_dubbed.mp4")
            cmd_dub = [
                "ffmpeg", "-y",
                "-i", final_video,
                "-i", ambient_path,
                "-filter_complex", "[1:a]volume=0.25[amb];[0:a][amb]amix=inputs=2:duration=first[outa]",
                "-map", "0:v", "-map", "[outa]",
                "-c:v", "copy", "-c:a", "aac",
                dubbed_path,
            ]
            result = subprocess.run(cmd_dub, capture_output=True)
            if result.returncode == 0:
                final_video = dubbed_path
                logger.info("Ambient audio mixed into final video")

        # ── 8. Send to Telegram ────────────────────────────────────────────
        logger.info("Stage 8: Sending to Telegram")
        type_cfg = _get_content_config(config, content_type)
        manual_mode = type_cfg["manual_mode"]

        caption = f"[{content_type.replace('_', ' ').title()}] {text[:100]}"
        telegram_send_video(final_video, caption)
        logger.info("Pipeline COMPLETE for %s", content_type)

        if not manual_mode:
            logger.info("Auto mode — also uploading to YouTube")
            try:
                from scripts.upload.youtube_upload import upload_video
                upload_video(
                    video_path=final_video,
                    title=script["title"],
                    description=script["description"],
                    tags=script["tags"],
                    privacy_status=type_cfg["privacy_status"],
                )
            except Exception as exc:
                logger.error("YouTube upload failed: %s", exc)
                telegram_send_message(f"[{content_type}] YouTube upload FAILED: {exc}")

    except Exception as exc:
        logger.error("Pipeline CRASHED for %s: %s", content_type, exc, exc_info=True)
        try:
            telegram_send_message(f"[{content_type}] Pipeline CRASHED: {exc}")
        except Exception:
            pass
        raise