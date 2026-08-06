import logging
import pathlib

from scripts.render.fast_text_renderer import render_segment

logger = logging.getLogger(__name__)


def render_all_segments(
    segments: list[dict],
    content_type: str,
    segments_audio: list[dict],
    output_dir: pathlib.Path,
) -> list[str]:
    """Render Manim scenes for all segments, matching each segment's audio duration."""
    output_dir.mkdir(parents=True, exist_ok=True)
    video_paths = []

    audio_by_id = {a["id"]: a for a in segments_audio}

    for segment in segments:
        audio_meta = audio_by_id[segment["id"]]
        seg_dir = output_dir / f"seg_{segment['id']:02d}"

        if segment.get("visual_type") == "image" and segment.get("image_path"):
            video_path = _make_image_video(segment["image_path"], audio_meta["total_duration"], seg_dir)
        else:
            video_path = render_segment(
                segment=segment,
                content_type=content_type,
                duration=audio_meta["total_duration"],
                output_dir=seg_dir,
            )
        video_paths.append(video_path)

    logger.info("Rendered %d segments", len(video_paths))
    return video_paths


def _make_image_video(image_path: str, duration: float, output_dir: pathlib.Path) -> str:
    """Convert a static image to a transparent MOV for compositing."""
    import subprocess
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / "image_overlay.mov")
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-t", str(duration),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black@0,fade=t=in:st=0:d=0.3:alpha=1",
        "-c:v", "qtrle",
        "-pix_fmt", "argb",
        "-r", "30",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path
