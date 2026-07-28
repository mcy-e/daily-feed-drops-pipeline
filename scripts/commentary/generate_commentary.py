import logging
import os
from google import genai
from scripts.constants import GEMINI_API_KEY_ENV_VAR

logger = logging.getLogger(__name__)

def generate_commentary(transcript_text: str) -> str:
    """Generate energetic sports commentary using Gemini based on original transcript."""
    api_key = os.getenv(GEMINI_API_KEY_ENV_VAR)
    if not api_key:
        raise ValueError(f"{GEMINI_API_KEY_ENV_VAR} is not set")
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    You are an energetic, humorous football (soccer) commentator. 
    Write a short, hype reaction line (around 30-40 words, no more) for a 15-20 second highlight clip.
    Use this original transcript for context on what is happening: "{transcript_text}"
    Do NOT include speaker labels, sound effects in brackets, or emojis. Just the spoken text.
    Make it sound natural, hype, and punchy.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
        )
        commentary = response.text.strip()
        logger.info("Generated commentary: %s", commentary)
        return commentary
    except Exception as exc:
        logger.error("Failed to generate commentary: %s", exc)
        raise
