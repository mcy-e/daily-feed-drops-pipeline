import logging
import pathlib
import subprocess

from scripts.render.image_card_renderer import render_image_card
from scripts.render.fast_text_renderer import render_segment as render_text_segment

logger = logging.getLogger(__name__)

# Content types that use TTS voice audio — duration comes from TTS length
VOICE_ENABLED_TYPES = {"meme_recap", "explained_topic", "quiz_riddle"}

# Reading speed fallback: words per second when no voice
READING_WORDS_PER_SECOND = 3.2
MIN_SEGMENT_DURATION = 3.0


def _reading_duration(text: str) -> float:
    """Estimate how long a viewer needs to read the given text."""
    word_count = len(text.split())
    return max(word_count / READING_WORDS_PER_SECOND, MIN_SEGMENT_DURATION)


def _image_to_video(image_path: str, duration: float, output_path: str) -> str:
    """Convert a static image to an MP4 video of the given duration."""
    fade_d = min(0.3, duration / 4)
    vf = (
        f"fade=t=in:st=0:d={fade_d}:alpha=1,"
        f"fade=t=out:st={max(0.0, duration - fade_d):.3f}:d={fade_d}:alpha=1"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        output_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Image-to-video failed: {exc.stderr[-300:]}") from exc
    return output_path


def render_all_segments(
    segments: list[dict],
    content_type: str,
    segments_audio: list[dict],
    output_dir: pathlib.Path,
) -> list[str]:
    """Render every segment as a video clip ready for compositing over B-Roll."""
    output_dir.mkdir(parents=True, exist_ok=True)
    video_paths = []
    audio_by_id = {a["id"]: a for a in segments_audio}
    voice_enabled = content_type in VOICE_ENABLED_TYPES

    for segment in segments:
        seg_id = segment["id"]
        audio_meta = audio_by_id[seg_id]
        seg_dir = output_dir / f"seg_{seg_id:02d}"
        seg_dir.mkdir(parents=True, exist_ok=True)

        # Duration: voice types use TTS length, non-voice types use reading time
        if voice_enabled:
            duration = audio_meta["total_duration"]
        else:
            display_text = segment.get("visual_content") or segment.get("narration", "")
            duration = _reading_duration(display_text)
            # Store back so the assembler uses the correct duration
            audio_meta["segment_duration"] = duration

        image_path = segment.get("image_path", "")
        has_image = bool(image_path) and pathlib.Path(image_path).exists()

        if has_image:
            display_text = segment.get("visual_content") or segment.get("narration", "")
            card_path = str(seg_dir / f"card_{seg_id:02d}.jpg")
            render_image_card(image_path, display_text, content_type, card_path)
            video_path = str(seg_dir / f"seg_{seg_id:02d}.mp4")
            _image_to_video(card_path, duration, video_path)
        else:
            # Fallback: text-only PIL card (transparent overlay)
            video_path = render_text_segment(
                segment=segment,
                content_type=content_type,
                duration=duration,
                output_dir=seg_dir,
            )

        video_paths.append(video_path)
        logger.info(
            "Segment %d rendered (%s, %.2fs, image=%s)",
            seg_id, content_type, duration, has_image,
        )

    logger.info("Rendered %d segments for %s", len(video_paths), content_type)
    return video_paths
