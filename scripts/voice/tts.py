import asyncio
import logging

import edge_tts

logger = logging.getLogger(__name__)

_DEFAULT_VOICE = "en-US-BrianNeural"
_DEFAULT_RATE = "+0%"
_DEFAULT_PITCH = "+0Hz"


async def generate_tts(
    text: str,
    dest_path: str,
    voice: str = _DEFAULT_VOICE,
    rate: str = _DEFAULT_RATE,
    pitch: str = _DEFAULT_PITCH,
) -> str | None:
    """Generate TTS audio file using edge-tts. Returns path on success."""
    try:
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(dest_path)
        return dest_path
    except Exception as exc:
        logger.error("TTS generation failed for voice=%s: %s", voice, exc)
        return None


def generate_tts_sync(
    text: str,
    dest_path: str,
    voice: str = _DEFAULT_VOICE,
    rate: str = _DEFAULT_RATE,
    pitch: str = _DEFAULT_PITCH,
) -> str | None:
    """Synchronous wrapper around generate_tts."""
    return asyncio.run(generate_tts(text, dest_path, voice=voice, rate=rate, pitch=pitch))
