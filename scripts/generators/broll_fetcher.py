import logging
import os
import pathlib
import random
import subprocess
import uuid

from scripts.utils.gdrive import download_file, get_drive_service, list_files

logger = logging.getLogger(__name__)

# Fallback YouTube gaming videos if Drive is empty
_FALLBACK_URLS = [
    "https://www.youtube.com/watch?v=n_Dv4JMmAO8",
    "https://www.youtube.com/watch?v=aHkLqNn_2dM",
    "https://www.youtube.com/watch?v=f2nNnJgA-tY",
    "https://www.youtube.com/watch?v=Wji-BZ0oC1w",
    "https://www.youtube.com/watch?v=XhxwGJaGqL8",
]

# Max bytes to pull from Drive per video (300 MB → ~5–15 min of footage at typical bitrates)
_MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024


def _video_duration(path: str) -> float:
    """Return decodable duration of a (possibly partial) video file in seconds."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip())
    except Exception as exc:
        logger.warning("ffprobe duration check failed: %s", exc)
        return 0.0


def _crop_and_scale(src: str, start: float, duration: float, dest: str) -> bool:
    """Crop a random section and scale to 1080x1920 portrait. No audio output."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(round(start, 3)),
        "-i", src,
        "-t", str(round(duration, 3)),
        "-vf", (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        dest,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("ffmpeg crop failed: %s", exc.stderr[-500:])
        return False


def _broll_from_drive(dest_dir: pathlib.Path, clip_duration: float) -> str | None:
    service = get_drive_service()
    folder_id = os.environ.get("GDRIVE_BROLL_FOLDER_ID")
    if not service or not folder_id:
        return None

    videos = list_files(service, folder_id, mime_prefix="video/")
    if not videos:
        logger.info("No videos found in Drive B-Roll folder.")
        return None

    chosen = random.choice(videos)
    raw = str(dest_dir / f"raw_{uuid.uuid4().hex[:8]}.mp4")
    logger.info("Downloading Drive B-Roll: %s", chosen["name"])

    if not download_file(service, chosen["id"], raw, max_bytes=_MAX_DOWNLOAD_BYTES):
        return None

    available = _video_duration(raw)
    if available < clip_duration + 5:
        logger.warning("Downloaded portion too short (%.1fs). Discarding.", available)
        pathlib.Path(raw).unlink(missing_ok=True)
        return None

    # Pick a truly random start anywhere within the decodable portion
    max_start = available - clip_duration - 2
    start = random.uniform(0, max(0, max_start))
    out = str(dest_dir / f"broll_{uuid.uuid4().hex[:8]}.mp4")

    if _crop_and_scale(raw, start, clip_duration, out):
        pathlib.Path(raw).unlink(missing_ok=True)
        logger.info("B-Roll cropped: start=%.1fs duration=%.1fs", start, clip_duration)
        return out

    pathlib.Path(raw).unlink(missing_ok=True)
    return None


def _broll_from_youtube(dest_dir: pathlib.Path, clip_duration: float) -> str | None:
    url = random.choice(_FALLBACK_URLS)
    start_sec = random.randint(300, 2700)
    raw = str(dest_dir / f"yt_{uuid.uuid4().hex[:8]}.mp4")

    logger.info("Downloading YouTube B-Roll (start=%ds): %s", start_sec, url)
    cmd = [
        "yt-dlp", "--force-ipv4",
        "--format", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
        "--download-sections", f"*{start_sec}-{start_sec + int(clip_duration) + 10}",
        "--output", raw,
        "--force-keyframes-at-cuts",
        url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("yt-dlp failed: %s", exc.stderr[-400:])
        return None

    out = str(dest_dir / f"broll_yt_{uuid.uuid4().hex[:8]}.mp4")
    if _crop_and_scale(raw, 0, clip_duration, out):
        pathlib.Path(raw).unlink(missing_ok=True)
        return out

    return None


def _black_fallback(dest_dir: pathlib.Path, clip_duration: float) -> str:
    out = str(dest_dir / "broll_black.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=black:s=1080x1920:r=30:d={clip_duration}",
            "-c:v", "libx264", "-preset", "fast", out,
        ],
        capture_output=True,
    )
    return out


def fetch_broll(dest_dir: pathlib.Path, clip_duration: float) -> str:
    """Fetch a gaming B-Roll video cropped to ``clip_duration`` seconds.

    Priority: Google Drive → YouTube → Black fallback.
    Each source picks a genuinely random segment — not always the start.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    result = _broll_from_drive(dest_dir, clip_duration)
    if result:
        return result

    logger.info("Drive B-Roll unavailable. Trying YouTube.")
    result = _broll_from_youtube(dest_dir, clip_duration)
    if result:
        return result

    logger.warning("All B-Roll sources failed. Using black fallback.")
    return _black_fallback(dest_dir, clip_duration)
