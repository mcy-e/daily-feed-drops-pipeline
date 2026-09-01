import logging
import os
import pathlib
import subprocess
import uuid

from scripts.utils.gdrive import download_file, find_file_by_name, get_drive_service

logger = logging.getLogger(__name__)

import random

def _fetch_ambient_sound(dest: pathlib.Path) -> str | None:
    """Fetch an ambient sound ('night_sound.mp3' or 'void.mp3') from Drive."""
    service = get_drive_service()
    if not service:
        return None

    folders = []
    if os.environ.get("GDRIVE_BROLL_FOLDER_ID"):
        folders.append(os.environ.get("GDRIVE_BROLL_FOLDER_ID"))
    if os.environ.get("GDRIVE_MEMES_FOLDER_ID"):
        folders.append(os.environ.get("GDRIVE_MEMES_FOLDER_ID"))

    sound_choice = random.choice(["night_sound.mp3", "void.mp3"])
    target = find_file_by_name(service, folders, sound_choice)
    
    if not target:
        logger.warning(f"{sound_choice} not found in Drive. Will use silent/ambient fallback.")
        return None

    out = str(dest)
    if download_file(service, target["id"], out):
        return out
    return None


def composite_meme(
    image_path: str,
    broll_path: str,
    output_dir: pathlib.Path,
) -> str:
    """Composite the meme image onto the B-Roll with ambient sound."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(output_dir / f"final_{uuid.uuid4().hex[:8]}.mp4")
    
    # 1. Fetch Audio
    audio_file = _fetch_ambient_sound(output_dir / "ambient.mp3")
    
    # 2. Get B-roll duration
    dur_cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        broll_path,
    ]
    try:
        duration = float(subprocess.run(dur_cmd, capture_output=True, text=True).stdout.strip())
    except:
        duration = 15.0 # Fallback
        
    logger.info(f"Compositing meme onto B-Roll (Duration: {duration}s)")
    
    # 3. Composite using FFmpeg
    # The image will be scaled to 800px width (leaving margins on 1080px canvas)
    # and placed in the top third (y=200).
    
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", broll_path,
        "-f", "image2", "-loop", "1", "-i", image_path
    ]
    
    if audio_file:
        cmd += ["-stream_loop", "-1", "-i", audio_file]
        
    # Scale image to 850px max width/height to fit nicely on screen
    # Add a slow upward drift (y=250 - t*8) to give it motion
    filter_complex = (
        "[1:v]scale=850:850:force_original_aspect_ratio=decrease[meme];"
        "[0:v][meme]overlay=(W-w)/2:'250-t*8':format=auto[outv]"
    )
    
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[outv]"
    ]
    
    if audio_file:
        # Lower volume significantly (was 0.25) and fade out in the last 1.5s
        audio_filter = f"volume=0.1,afade=t=out:st={max(0, duration - 1.5):.3f}:d=1.5"
        cmd += ["-map", "2:a", "-filter:a", audio_filter]
    else:
        # Fallback synthetic brown noise at low volume
        cmd += ["-f", "lavfi", "-i", "anoisesrc=c=brown:r=44100:a=0.1", "-map", "2:a"]
        
    cmd += [
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        out_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return out_path
    except subprocess.CalledProcessError as exc:
        logger.error(f"Failed to composite final video: {exc.stderr[-500:]}")
        raise RuntimeError("Composition failed") from exc
