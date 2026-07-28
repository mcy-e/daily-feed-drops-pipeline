import logging
import subprocess

logger = logging.getLogger(__name__)

# Using a high-energy preset from edge-tts
TTS_VOICE = "en-US-ChristopherNeural"

def generate_tts(text: str, output_base_path: str) -> tuple[str, str]:
    """
    Generate TTS audio and VTT subtitles using edge-tts.
    Returns (audio_path, vtt_path)
    """
    audio_path = f"{output_base_path}_tts.mp3"
    vtt_path = f"{output_base_path}_tts.vtt"
    
    cmd = [
        "python", "-c",
        "import ssl, sys; ssl.create_default_context = ssl._create_unverified_context; "
        "from edge_tts.util import main; sys.exit(main())",
        "--text", text,
        "--voice", TTS_VOICE,
        "--write-media", audio_path,
        "--write-subtitles", vtt_path
    ]
    
    try:
        logger.info("Generating TTS for text (length %d)...", len(text))
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("Generated TTS audio at %s and VTT at %s", audio_path, vtt_path)
        return audio_path, vtt_path
    except subprocess.CalledProcessError as exc:
        logger.error("edge-tts failed: %s", exc.stderr)
        raise RuntimeError(f"TTS generation failed: {exc.stderr}") from exc
