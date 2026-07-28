import json
import logging
import os
import pathlib
import subprocess

from scripts.constants import (
    MANIM_FRAME_HEIGHT,
    MANIM_FRAME_WIDTH,
    MANIM_PIXEL_HEIGHT,
    MANIM_PIXEL_WIDTH,
    PROJECT_ROOT,
)

logger = logging.getLogger(__name__)

SEGMENT_SCENE_MODULE = "scripts.manim_scenes.segment_scene"
SEGMENT_SCENE_CLASS = "SegmentScene"


def render_segment(
    segment: dict,
    content_type: str,
    duration: float,
    output_dir: pathlib.Path,
    quality: str = "l",
) -> str:
    """Render a single segment as a Manim scene. Returns path to rendered MP4."""
    output_dir.mkdir(parents=True, exist_ok=True)

    config_path = output_dir / f"seg_{segment['id']:02d}_config.json"
    config_data = {
        "segment": segment,
        "content_type": content_type,
        "duration": duration,
    }
    config_path.write_text(json.dumps(config_data), encoding="utf-8")

    env = os.environ.copy()
    env["CONTENT_SEGMENT_CONFIG"] = str(config_path.resolve())
    
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{PROJECT_ROOT}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = str(PROJECT_ROOT)

    scene_file = PROJECT_ROOT / "scripts" / "manim_scenes" / "segment_scene.py"

    cmd = [
        "manim",
        "render",
        f"-q{quality}",
        "--format", "mp4",
        "-r", f"{MANIM_PIXEL_WIDTH},{MANIM_PIXEL_HEIGHT}",
        "--media_dir", str(output_dir),
        "--disable_caching",
        str(scene_file),
        SEGMENT_SCENE_CLASS,
    ]

    logger.info("Rendering Manim scene for segment %d (%.2fs)", segment["id"], duration)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, env=env,
            cwd=str(PROJECT_ROOT),
        )
        if result.stderr:
            logger.debug("Manim stderr: %s", result.stderr[-500:])
    except subprocess.CalledProcessError as exc:
        logger.error("Manim render failed: %s", exc.stderr)
        raise RuntimeError(f"Manim render failed for segment {segment['id']}: {exc.stderr}") from exc

    rendered = _find_rendered_video(output_dir, SEGMENT_SCENE_CLASS)
    if not rendered:
        raise RuntimeError(f"Manim output not found for segment {segment['id']}")

    logger.info("Segment %d rendered: %s", segment["id"], rendered)
    return str(rendered)


def _find_rendered_video(media_dir: pathlib.Path, scene_class: str) -> pathlib.Path | None:
    """Locate the rendered MP4 in Manim's media directory structure."""
    candidates = list(media_dir.rglob(f"{scene_class}.mp4"))
    if candidates:
        return max(candidates, key=lambda p: p.stat().st_mtime)

    for sub in ["videos", "media"]:
        search = media_dir / sub
        if search.exists():
            found = list(search.rglob("*.mp4"))
            if found:
                return max(found, key=lambda p: p.stat().st_mtime)
    return None
