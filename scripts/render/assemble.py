import logging
import os
import pathlib
import subprocess

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

AMBIENT_VOLUME = "0.18"

def _generate_ambient(dest: pathlib.Path) -> str | None:
    """Generate continuous non-repeating nature ambient sound (wind/water) using FFmpeg noise."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    out_path = str(dest)
    # Pink noise + Brown noise mixed together creates a very convincing continuous river/wind sound
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "anoisesrc=c=brown:r=44100:a=0.15",
        "-i", "anoisesrc=c=pink:r=44100:a=0.08",
        "-filter_complex", "amix=inputs=2:duration=first",
        "-t", "120",  # Generate 2 minutes max
        "-c:a", "aac",
        out_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info("Continuous ambient audio generated: %s", out_path)
        return out_path
    except Exception as exc:
        logger.warning("Ambient generation failed: %s", exc)
        return None


def _get_segment_duration(audio_meta: dict) -> float:
    """Return the display duration — reading-time override takes precedence over TTS."""
    return audio_meta.get("segment_duration") or audio_meta["total_duration"]


def composite_segment_on_broll(
    broll_path: str,
    segment_video_path: str,
    audio_path: str,
    output_path: str,
    total_duration: float,
    ambient_path: str | None = None,
) -> str:
    """Composite a segment video card on top of B-Roll with TTS + optional ambient audio."""
    # Check if the segment video is already a full MP4 (image card) or a transparent MOV overlay
    seg_ext = pathlib.Path(segment_video_path).suffix.lower()
    is_opaque = seg_ext == ".mp4"

    if is_opaque:
        # The segment is a full opaque MP4 image card — scale and center it on the B-Roll
        filter_graph = (
            "[0:v]loop=loop=-1:size=32767:start=0,"
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,setpts=PTS-STARTPTS[bg];"
            "[1:v]scale=900:-2:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black@0,"
            "setpts=PTS-STARTPTS[card];"
            "[bg][card]overlay=(W-w)/2:(H-h)/2:format=auto[out]"
        )
    else:
        # Transparent MOV overlay (text card fallback)
        filter_graph = (
            "[0:v]loop=loop=-1:size=32767:start=0,"
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,setpts=PTS-STARTPTS[bg];"
            "[1:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black@0,"
            "setpts=PTS-STARTPTS[fg];"
            "[bg][fg]overlay=0:0:format=auto[out]"
        )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", broll_path,
        "-i", segment_video_path,
        "-i", audio_path,
    ]

    if ambient_path:
        cmd += ["-stream_loop", "-1", "-i", ambient_path]
        audio_filter = (
            f"[2:a]volume=1.0[tts];"
            f"[3:a]volume={AMBIENT_VOLUME}[amb];"
            f"[tts][amb]amix=inputs=2:duration=first[aout]"
        )
        full_filter = f"{filter_graph};{audio_filter}"
        cmd += [
            "-filter_complex", full_filter,
            "-map", "[out]",
            "-map", "[aout]",
        ]
    else:
        cmd += [
            "-filter_complex", filter_graph,
            "-map", "[out]",
            "-map", "2:a:0",
        ]

    cmd += [
        "-t", str(total_duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]

    logger.info(
        "Compositing segment: broll=%s + card=%s (%.2fs)",
        pathlib.Path(broll_path).name,
        pathlib.Path(segment_video_path).name,
        total_duration,
    )
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("Composite failed: %s", exc.stderr[-600:])
        raise RuntimeError(f"Composite failed: {exc.stderr[-300:]}") from exc
    return output_path


def _make_silent_audio(duration: float, output_path: str) -> str:
    """Generate a silent audio track of the given duration."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        "-c:a", "aac",
        output_path,
    ]
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
    broll_path: str = None,
) -> str:
    """Composite image cards onto B-Roll with ambient audio, then concatenate. Returns final video path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    ambient_path = _generate_ambient(output_dir / "ambient.aac")

    composited_paths = []
    for video, audio_meta in zip(segment_videos, segment_audios):
        seg_duration = _get_segment_duration(audio_meta)
        out = str(output_dir / f"composited_{audio_meta['id']:02d}.mp4")

        audio_path = audio_meta["audio_path"]

        # For non-voice segments, the audio may be silence — check file size
        if not pathlib.Path(audio_path).exists() or pathlib.Path(audio_path).stat().st_size < 512:
            silent_path = str(output_dir / f"silent_{audio_meta['id']:02d}.aac")
            audio_path = _make_silent_audio(seg_duration, silent_path)

        if broll_path:
            composite_segment_on_broll(
                broll_path, video, audio_path, out, seg_duration, ambient_path
            )
        else:
            from scripts.constants import FFMPEG_CRF, FFMPEG_PRESET
            cmd = [
                "ffmpeg", "-y",
                "-i", video,
                "-i", audio_path,
                "-map", "0:v:0", "-map", "1:a:0",
                "-t", str(seg_duration),
                "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-crf", str(FFMPEG_CRF),
                "-c:a", "aac",
                out,
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True)

        composited_paths.append(out)

    final_path = str(output_dir / "final.mp4")
    concatenate_segments(composited_paths, final_path)

    logger.info("Assembly complete: %s", final_path)
    return final_path
