import logging
import pathlib

from scripts.render.manim_render import render_segment

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
        video_path = render_segment(
            segment=segment,
            content_type=content_type,
            duration=audio_meta["total_duration"],
            output_dir=seg_dir,
        )
        video_paths.append(video_path)

    logger.info("Rendered %d Manim segments", len(video_paths))
    return video_paths
