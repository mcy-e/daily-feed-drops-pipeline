import json
import logging
import subprocess

from scripts.constants import TTS_VOICE
from scripts.render.render import probe_video

logger = logging.getLogger(__name__)

VOICE_ENABLED_TYPES = {"meme_recap", "explained_topic", "quiz_riddle"}


def _probe_audio_duration(audio_path: str) -> float:
    """Get audio duration via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a:0",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if streams:
        return float(streams[0].get("duration", 0))
    return probe_video(audio_path).get("duration", 0)


def generate_segment_audio(
    segment: dict,
    output_dir: str,
    voice: str = TTS_VOICE,
    content_type: str = "",
) -> dict:
    """Generate TTS audio for one segment. Returns segment metadata with audio_path and duration.
    
    For non-voice content types, returns a silent stub — reading-time duration is computed in scene_builder.
    """
    seg_id = segment["id"]
    narration = segment["narration"]
    audio_path = f"{output_dir}/seg_{seg_id:02d}.mp3"

    if content_type and content_type not in VOICE_ENABLED_TYPES:
        # Create a 0-byte stub so assembler knows audio is absent
        open(audio_path, "wb").close()
        return {
            "id": seg_id,
            "audio_path": audio_path,
            "narration": narration,
            "duration": 0.0,
            "pause_after": 0.0,
            "total_duration": 0.0,
        }

    import requests
    import base64
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # TikTok TTS viral voice (en_us_001 = Jessie/enthusiastic female, en_us_006 = deep male)
    voice_id = "en_us_001"
    
    logger.info("Generating TikTok TTS for segment %d (len=%d) using voice %s", seg_id, len(narration), voice_id)
    
    try:
        response = requests.post(
            "https://tiktok-tts.weilnet.workers.dev/api/generation",
            json={"text": narration, "voice": voice_id},
            verify=False,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if not data.get("success"):
            raise RuntimeError(f"TikTok TTS API returned error: {data}")
            
        audio_b64 = data.get("data")
        if not audio_b64:
            raise RuntimeError("No audio data returned from TikTok TTS")
            
        with open(audio_path, "wb") as f:
            f.write(base64.b64decode(audio_b64))
            
    except Exception as exc:
        logger.error("TikTok TTS failed: %s", exc)
        raise RuntimeError(f"TikTok TTS generation failed: {exc}") from exc

    duration = _probe_audio_duration(audio_path)
    pause_after = float(segment.get("pause_after", 0.5))
    total_duration = duration + pause_after

    logger.info("Segment %d audio: %.2fs (+ %.2fs pause)", seg_id, duration, pause_after)

    return {
        "id": seg_id,
        "audio_path": audio_path,
        "narration": narration,
        "duration": duration,
        "pause_after": pause_after,
        "total_duration": total_duration,
    }


def generate_all_segment_audio(segments: list[dict], output_dir: str, content_type: str = "") -> list[dict]:
    """Generate TTS for all segments. Returns list of audio metadata dicts."""
    return [generate_segment_audio(seg, output_dir, content_type=content_type) for seg in segments]
