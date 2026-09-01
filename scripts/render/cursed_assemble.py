import logging
import pathlib
import subprocess
import uuid
import os

from scripts.voice.tts import generate_tts_sync

logger = logging.getLogger(__name__)

_SETUP_VOICE = "en-US-BrianNeural"
_SETUP_RATE = "+0%"
_SETUP_PITCH = "+0Hz"

_PUNCHLINE_VOICE = "en-US-BrianNeural"
_PUNCHLINE_RATE = "-15%"
_PUNCHLINE_PITCH = "-20Hz"

_FONT_PATH = "C\\\\:/Windows/Fonts/arialbd.ttf"  # Assuming Windows Arial Bold
_SILENCE_DUR = 1.5


def _get_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        return float(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip())
    except Exception as exc:
        logger.warning("Failed to probe duration for %s: %s", path, exc)
        return 0.0


def _create_silence(dest_path: str, duration: float) -> str:
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", str(duration), dest_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return dest_path


def _render_segment(
    dest_path: str,
    duration: float,
    audio_path: str,
    bg_video_path: str | None,
    text_content: str,
) -> str:
    """Renders a single video segment with wrapped text and audio."""
    cmd = ["ffmpeg", "-y"]
    
    if bg_video_path:
        cmd.extend(["-stream_loop", "-1", "-i", bg_video_path])
    else:
        cmd.extend(["-f", "lavfi", "-i", "color=c=#0a0a0a:s=1080x1920:r=30"])

    cmd.extend(["-i", audio_path])
    
    # Escape single quotes and colons for drawtext
    escaped_text = text_content.replace("'", "\\'").replace(":", "\\:")
    
    drawtext_filter = (
        f"drawtext=fontfile='{_FONT_PATH}':text='{escaped_text}':"
        f"fontcolor=white:fontsize=52:box=1:boxcolor=black@0.6:boxborderw=10:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=2:shadowy=2:borderw=1:"
        f"fix_bounds=true"
    )
    
    # Actually drawtext doesn't word wrap easily without setting a max width
    # We'll rely on the text being somewhat short, or split by newlines prior to this.
    # An alternative is creating a subtitles SRT, but drawtext is simpler for this POC.

    cmd.extend([
        "-filter_complex", f"[0:v]{drawtext_filter}[outv]",
        "-map", "[outv]",
        "-map", "1:a",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        dest_path
    ])
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return dest_path
    except subprocess.CalledProcessError as exc:
        logger.error("FFmpeg segment render failed: %s", exc.stderr[-500:])
        raise RuntimeError(f"Segment render failed: {exc}") from exc


def render_cursed_clip(
    item: dict,
    dest_dir: pathlib.Path,
    bg_video_path: str | None = None,
) -> str | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    clip_id = uuid.uuid4().hex[:8]
    
    setup_audio = str(dest_dir / f"setup_{clip_id}.mp3")
    punchline_audio = str(dest_dir / f"punchline_{clip_id}.mp3")
    
    if not generate_tts_sync(item["setup"], setup_audio, voice=_SETUP_VOICE, rate=_SETUP_RATE, pitch=_SETUP_PITCH):
        return None
        
    if not generate_tts_sync(item["punchline"], punchline_audio, voice=_PUNCHLINE_VOICE, rate=_PUNCHLINE_RATE, pitch=_PUNCHLINE_PITCH):
        return None

    setup_dur = _get_duration(setup_audio)
    punchline_dur = _get_duration(punchline_audio)
    
    if setup_dur == 0 or punchline_dur == 0:
        return None

    # We add 1.5s of padding to each segment
    seg_a_dur = setup_dur + _SILENCE_DUR
    seg_b_dur = punchline_dur + _SILENCE_DUR
    
    # Create padded audio
    silence_audio = str(dest_dir / f"sil_{clip_id}.m4a")
    _create_silence(silence_audio, _SILENCE_DUR)
    
    # We need to concat the speech and silence for each segment
    padded_setup_audio = str(dest_dir / f"pad_setup_{clip_id}.m4a")
    subprocess.run([
        "ffmpeg", "-y", "-i", setup_audio, "-i", silence_audio,
        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[outa]",
        "-map", "[outa]", "-c:a", "aac", padded_setup_audio
    ], capture_output=True, check=True)
    
    padded_punchline_audio = str(dest_dir / f"pad_punchline_{clip_id}.m4a")
    subprocess.run([
        "ffmpeg", "-y", "-i", punchline_audio, "-i", silence_audio,
        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[outa]",
        "-map", "[outa]", "-c:a", "aac", padded_punchline_audio
    ], capture_output=True, check=True)

    # Format text for Drawtext (inserting basic newlines for wrapping)
    # Very crude word wrap: split every ~30 chars
    def wrap_text(t, width=30):
        words = t.split()
        lines = []
        cur = []
        for w in words:
            if len(" ".join(cur + [w])) > width:
                lines.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        if cur:
            lines.append(" ".join(cur))
        return "\n".join(lines)

    setup_text = wrap_text(item["setup"])
    punchline_text = wrap_text(item["punchline"])
    combined_text = f"{setup_text}\n\n-------------\n\n{punchline_text}"

    seg_a_path = str(dest_dir / f"segA_{clip_id}.mp4")
    seg_b_path = str(dest_dir / f"segB_{clip_id}.mp4")

    logger.info("Rendering Segment A for clip %s", clip_id)
    _render_segment(seg_a_path, seg_a_dur, padded_setup_audio, bg_video_path, setup_text)
    
    logger.info("Rendering Segment B for clip %s", clip_id)
    _render_segment(seg_b_path, seg_b_dur, padded_punchline_audio, bg_video_path, combined_text)
    
    # Concat Segment A and B
    concat_txt = dest_dir / f"concat_{clip_id}.txt"
    concat_txt.write_text(f"file '{os.path.basename(seg_a_path)}'\nfile '{os.path.basename(seg_b_path)}'")
    
    final_clip_path = str(dest_dir / f"clip_{clip_id}.mp4")
    
    logger.info("Concatenating into final clip %s", final_clip_path)
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy",
        final_clip_path
    ], capture_output=True, check=True)
    
    return final_clip_path
