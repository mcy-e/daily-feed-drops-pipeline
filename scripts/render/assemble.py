import logging
import os
import pathlib
import subprocess

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Vertical position of the card top edge — top third of a 1920px reel
CARD_OVERLAY_Y = 280
# Card render width — must match image_card_renderer.CARD_W
CARD_OVERLAY_W = 700


import random
import uuid

AMBIENT_VIDEOS = [
    "https://www.youtube.com/watch?v=njCDZWTI-xg", # 10 hours crickets and owls
    "https://www.youtube.com/watch?v=1sJ7nL-JzH0", # 10 hours night ambience
    "https://www.youtube.com/watch?v=W0oZfWwBweU", # Night crickets
]

def _generate_ambient(dest: pathlib.Path, duration: float = 120.0) -> str | None:
    """Fetch a real, random slice of night ambient audio (crickets/owls) via yt-dlp."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    out_path = str(dest)
    
    video_url = random.choice(AMBIENT_VIDEOS)
    # Pick a random start time in the first 5 hours of the 10-hour video
    start_time = random.randint(300, 18000)
    
    logger.info("Fetching real ambient audio slice from %s", video_url)
    cmd = [
        "yt-dlp",
        "--force-ipv4",
        "--format", "bestaudio[ext=m4a]/bestaudio/best",
        "--download-sections", f"*{start_time}-{start_time + duration + 5}",
        "--output", out_path,
        "--force-keyframes-at-cuts",
        video_url
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return out_path
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to fetch real ambient audio: %s. Falling back to synth.", exc.stderr)
        
        # Synthetic fallback if yt-dlp fails
        synth_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anoisesrc=c=brown:r=44100:a=0.4",
            "-t", str(duration),
            "-c:a", "aac", "-b:a", "128k",
            out_path,
        ]
        subprocess.run(synth_cmd, capture_output=True, text=True, check=True)
        return out_path
    except Exception as exc:
        logger.warning("Ambient generation exception: %s", exc)
        return None


def _get_segment_duration(audio_meta: dict) -> float:
    return audio_meta.get("segment_duration") or audio_meta["total_duration"]


def composite_segment_on_broll(
    broll_path: str,
    card_video_path: str,
    audio_path: str,
    output_path: str,
    total_duration: float,
    ambient_path: str | None = None,
) -> str:
    """Overlay the card video on B-Roll. Card is a small MP4, not a full-frame video.
    Positioned in the top third. Audio is ambient only (no voice TTS for these types)."""

    # Overlay: B-Roll fills full 1080x1920, card is placed at top-third position
    filter_graph = (
        "[0:v]loop=loop=-1:size=32767:start=0,"
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,setpts=PTS-STARTPTS[bg];"
        f"[1:v]scale={CARD_OVERLAY_W}:-2,setpts=PTS-STARTPTS[card];"
        f"[bg][card]overlay=(W-w)/2:{CARD_OVERLAY_Y}:format=auto[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", broll_path,
        "-i", card_video_path,
    ]

    if ambient_path and pathlib.Path(ambient_path).exists():
        # Use ambient as the sole audio track — no silent TTS track to dilute it
        cmd += ["-stream_loop", "-1", "-i", ambient_path]
        audio_filter = "[2:a]volume=1.8[aout]"
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
            "-an",
        ]

    cmd += [
        "-t", str(total_duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]

    logger.info(
        "Compositing: broll=%s + card=%s (%.2fs)",
        pathlib.Path(broll_path).name,
        pathlib.Path(card_video_path).name,
        total_duration,
    )
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("Composite failed: %s", exc.stderr[-800:])
        raise RuntimeError(f"Composite failed: {exc.stderr[-400:]}") from exc
    return output_path


def _make_silent_audio(duration: float, output_path: str) -> str:
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        "-c:a", "aac",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path


def concatenate_segments(segment_paths: list[str], output_path: str) -> str:
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
    """Overlay card videos onto B-Roll with ambient audio. Returns final video path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    total_video_duration = sum(_get_segment_duration(a) for a in segment_audios)
    ambient_path = _generate_ambient(output_dir / "ambient.m4a", duration=total_video_duration)

    composited_paths = []
    for video, audio_meta in zip(segment_videos, segment_audios):
        seg_duration = _get_segment_duration(audio_meta)
        out = str(output_dir / f"composited_{audio_meta['id']:02d}.mp4")

        if broll_path:
            composite_segment_on_broll(
                broll_path, video, audio_meta["audio_path"], out, seg_duration, ambient_path
            )
        else:
            # No B-Roll fallback: just encode the card video with ambient audio
            cmd = [
                "ffmpeg", "-y",
                "-i", video,
            ]
            if ambient_path and pathlib.Path(ambient_path).exists():
                cmd += ["-stream_loop", "-1", "-i", ambient_path]
                cmd += [
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-t", str(seg_duration),
                    "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-crf", "23",
                    "-c:a", "aac", "-b:a", "192k",
                    out,
                ]
            else:
                cmd += [
                    "-map", "0:v:0", "-an",
                    "-t", str(seg_duration),
                    "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-crf", "23",
                    out,
                ]
            subprocess.run(cmd, capture_output=True, text=True, check=True)

        composited_paths.append(out)

    final_path = str(output_dir / "final.mp4")
    concatenate_segments(composited_paths, final_path)

    logger.info("Assembly complete: %s", final_path)
    return final_path
