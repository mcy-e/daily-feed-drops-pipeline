import logging
import pathlib
import subprocess

logger = logging.getLogger(__name__)


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(segments_audio: list[dict]) -> str:
    """Build cumulative SRT content from segment narration and durations."""
    lines = []
    cumulative = 0.0

    for idx, seg in enumerate(segments_audio, start=1):
        start = cumulative
        end = cumulative + seg["duration"]
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
        lines.append(seg["narration"])
        lines.append("")
        cumulative = end + seg.get("pause_after", 0.5)

    return "\n".join(lines)


def mux_segment(video_path: str, audio_path: str, output_path: str, total_duration: float) -> str:
    """Mux a Manim video with its TTS audio track, preserving the full segment duration."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-t", str(total_duration),
        "-c:v", "copy",
        "-c:a", "aac",
        output_path,
    ]
    logger.info("Muxing segment: %s + %s", pathlib.Path(video_path).name, pathlib.Path(audio_path).name)
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path


def concatenate_segments(segment_paths: list[str], output_path: str) -> str:
    """Concatenate muxed segment videos into one file."""
    if len(segment_paths) == 1:
        pathlib.Path(output_path).write_bytes(pathlib.Path(segment_paths[0]).read_bytes())
        return output_path

    list_file = pathlib.Path(output_path).with_suffix(".txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for p in segment_paths:
            escaped = str(pathlib.Path(p).resolve()).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        output_path,
    ]
    logger.info("Concatenating %d segments", len(segment_paths))
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    list_file.unlink(missing_ok=True)
    return output_path


def assemble_video(
    segment_videos: list[str],
    segment_audios: list[dict],
    output_dir: pathlib.Path,
) -> tuple[str, str]:
    """Mux, concatenate segments, and write SRT. Returns (video_path, srt_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    muxed_paths = []
    for video, audio_meta in zip(segment_videos, segment_audios):
        muxed = str(output_dir / f"muxed_{audio_meta['id']:02d}.mp4")
        mux_segment(video, audio_meta["audio_path"], muxed, audio_meta["total_duration"])
        muxed_paths.append(muxed)

    assembled_path = str(output_dir / "assembled.mp4")
    concatenate_segments(muxed_paths, assembled_path)

    srt_content = build_srt(segment_audios)
    srt_path = str(output_dir / "captions.srt")
    pathlib.Path(srt_path).write_text(srt_content, encoding="utf-8")

    logger.info("Assembly complete: %s", assembled_path)
    return assembled_path, srt_path
