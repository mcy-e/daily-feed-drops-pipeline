import json
import logging
import pathlib
import subprocess
import time
import uuid

from scripts.constants import (
    BLUR_SIGMA,
    DEFAULT_OUTPUT_DIR,
    FFMPEG_CRF,
    FFMPEG_PRESET,
    RENDER_HEIGHT,
    RENDER_WIDTH,
)

logger = logging.getLogger(__name__)


def probe_video(input_path: str | pathlib.Path) -> dict:
    """Extract video stream metadata via ffprobe."""
    input_path = pathlib.Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        str(input_path),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
        probe_data = json.loads(result.stdout)
        streams = probe_data.get("streams", [])

        if not streams:
            raise RuntimeError(f"No video stream found in {input_path}")

        stream = streams[0]
        return {
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "duration": float(stream.get("duration", 0)),
        }

    except subprocess.CalledProcessError as exc:
        logger.error("ffprobe failed: %s", exc.stderr)
        raise RuntimeError(f"ffprobe failed for {input_path}: {exc.stderr}") from exc
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Failed to parse ffprobe output: %s", exc)
        raise RuntimeError(f"ffprobe output parsing failed: {exc}") from exc


def build_filter_graph(src_width: int, src_height: int, srt_path: str = None) -> str:
    """
    Build an ffmpeg filter graph for scale-to-fit with blurred background.

    The source video is split into two streams:
    - Background: scaled up to cover 1080x1920, cropped, then Gaussian blurred.
    - Foreground: scaled to fit inside 1080x1920 with aspect ratio preserved.
    The foreground is overlaid centred on the blurred background.
    """
    w = RENDER_WIDTH
    h = RENDER_HEIGHT

    fg_scale = min(w / src_width, h / src_height)
    fg_w = int(src_width * fg_scale)
    fg_h = int(src_height * fg_scale)

    # Ensure even dimensions for libx264 compatibility
    fg_w = fg_w - (fg_w % 2)
    fg_h = fg_h - (fg_h % 2)

    overlay_x = (w - fg_w) // 2
    overlay_y = (h - fg_h) // 2

    # Optional subtitles filter
    subs_filter = ""
    if srt_path:
        # Escape path for FFmpeg subtitles filter on Windows/Linux and wrap in quotes
        escaped_srt = str(srt_path).replace("\\", "/").replace(":", "\\:")
        subs_filter = f",subtitles='{escaped_srt}'"

    filter_graph = (
        f"split[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},gblur=sigma={BLUR_SIGMA}[blurred];"
        f"[fg]scale={fg_w}:{fg_h}{subs_filter}[sharp];"
        f"[blurred][sharp]overlay={overlay_x}:{overlay_y}"
    )

    logger.info(
        "Filter graph built — source %dx%d → fg %dx%d on %dx%d blurred bg",
        src_width, src_height, fg_w, fg_h, w, h,
    )
    return filter_graph


def render_video(
    input_path: str | pathlib.Path,
    output_dir: str | pathlib.Path = DEFAULT_OUTPUT_DIR,
    start_time: float = None,
    end_time: float = None,
    srt_path: str = None,
) -> str:
    """Render a video to 9:16 with blurred-background padding. Returns output path."""
    input_path = pathlib.Path(input_path)
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    probe = probe_video(input_path)
    filter_graph = build_filter_graph(probe["width"], probe["height"], srt_path)

    output_name = f"{input_path.stem}_rendered.mp4"
    output_path = output_dir / output_name

    cmd = ["ffmpeg"]
    if start_time is not None:
        cmd.extend(["-ss", str(start_time)])
    if end_time is not None:
        cmd.extend(["-to", str(end_time)])
        
    cmd.extend([
        "-i", str(input_path),
        "-vf", filter_graph,
        "-c:v", "libx264",
        "-preset", FFMPEG_PRESET,
        "-crf", str(FFMPEG_CRF),
        "-c:a", "aac",
        "-y",
        str(output_path),
    ])

    logger.info("Starting render: %s → %s", input_path.name, output_path.name)
    start_time = time.time()

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as exc:
        logger.error("ffmpeg render failed: %s", exc.stderr)
        raise RuntimeError(f"ffmpeg render failed: {exc.stderr}") from exc

    elapsed = time.time() - start_time
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Render complete in %.1fs — output: %s (%.1f MB)",
        elapsed, output_path.name, file_size_mb,
    )

    return str(output_path)
