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


def composite_segment_on_broll(
    broll_path: str,
    manim_overlay_path: str,
    audio_path: str,
    output_path: str,
    total_duration: float,
) -> str:
    """Overlay transparent Manim MOV on top of B-Roll video with TTS audio."""
    filter_graph = (
        "[0:v]loop=loop=-1:size=32767:start=0,"
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setpts=PTS-STARTPTS[bg];"
        "[1:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black@0,setpts=PTS-STARTPTS[fg];"
        "[bg][fg]overlay=0:0:format=auto[out]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", broll_path,
        "-i", manim_overlay_path,
        "-i", audio_path,
        "-filter_complex", filter_graph,
        "-map", "[out]",
        "-map", "2:a:0",
        "-t", str(total_duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    logger.info(
        "Compositing segment: broll=%s + manim=%s",
        pathlib.Path(broll_path).name, pathlib.Path(manim_overlay_path).name,
    )
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("Composite failed: %s", exc.stderr[-500:])
        raise RuntimeError(f"Composite failed: {exc.stderr[-300:]}") from exc
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
    broll_path: str = None,
) -> str:
    """Composite Manim overlays onto B-Roll (or fallback blur-pad), then concatenate. Returns final video path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    composited_paths = []
    for video, audio_meta in zip(segment_videos, segment_audios):
        out = str(output_dir / f"composited_{audio_meta['id']:02d}.mp4")
        if broll_path:
            composite_segment_on_broll(
                broll_path, video, audio_meta["audio_path"], out, audio_meta["total_duration"]
            )
        else:
            # Fallback: simple mux without B-Roll
            from scripts.constants import FFMPEG_CRF, FFMPEG_PRESET, RENDER_WIDTH, RENDER_HEIGHT, BLUR_SIGMA
            filter_graph = (
                "split[bg][fg];"
                f"[bg]scale={RENDER_WIDTH}:{RENDER_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={RENDER_WIDTH}:{RENDER_HEIGHT},gblur=sigma={BLUR_SIGMA}[blurred];"
                f"[fg]scale={RENDER_WIDTH}:{RENDER_HEIGHT}[sharp];"
                "[blurred][sharp]overlay=(W-w)/2:(H-h)/2"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", video, "-i", audio_meta["audio_path"],
                "-filter_complex", filter_graph,
                "-map", "[sharp]", "-map", "1:a:0",
                "-t", str(audio_meta["total_duration"]),
                "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-crf", str(FFMPEG_CRF),
                "-c:a", "aac", out,
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        composited_paths.append(out)

    final_path = str(output_dir / "final.mp4")
    concatenate_segments(composited_paths, final_path)

    logger.info("Assembly complete: %s", final_path)
    return final_path
