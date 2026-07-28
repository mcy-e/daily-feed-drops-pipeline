import json
import logging
import os
import random
import re

from google import genai

from scripts.constants import (
    CONTENT_TOPIC_POOLS,
    CONTENT_TYPES,
    GEMINI_API_KEY_ENV_VAR,
    GEMINI_TEXT_MODEL,
)
from scripts.generators.news_fetcher import fetch_current_headline

logger = logging.getLogger(__name__)

SCRIPT_SCHEMA = """
{
  "title": "string — catchy video title",
  "segments": [
    {
      "id": 1,
      "narration": "string — spoken text for TTS",
      "visual_type": "text | number | list | shape | image",
      "visual_content": "string — on-screen visual payload",
      "image_needed": false,
      "image_query": "string — Pexels search query if image_needed",
      "image_path": "",
      "pause_after": 0.5
    }
  ]
}
"""

CONTENT_PROMPTS = {
    "explained_topic": """Create a 45-60 second short-form explainer video script about: {topic}

Style: clean, minimal, educational. Use visual_type "text" for key concepts, "list" for steps, "number" for stats.
Requirements:
- Open with a STRONG HOOK line that grabs attention immediately
- Short, punchy sentences throughout (max 15 words each)
- Include a pattern-interrupt or surprising reveal around the middle
- 5-7 segments total
- visual_content should be concise on-screen text (not the full narration)""",

    "kids_content": """Create a 45-60 second fun facts video for kids about: {topic}

Style: bright, bold, energetic. Use visual_type "text" and "list" primarily, "number" for wow-stats.
Requirements:
- Open with a STRONG HOOK that makes kids say "whoa!"
- Short, punchy sentences (max 12 words)
- Pattern-interrupt or fun reveal midway
- 5-7 segments
- Keep language simple and exciting""",

    "football_trivia": """Create a 45-60 second football trivia video about: {topic}

Style: stat-card format. Use visual_type "number" for the key stat, "text" for context.
Requirements:
- Open with a STRONG HOOK teasing the stat
- Short, punchy sentences
- Build suspense, then reveal the answer as a pattern-interrupt
- 5-6 segments
- visual_content for numbers should be the stat itself (e.g. "873 goals")""",

    "viral_news": """Turn this REAL current news headline into a 45-60 second viral news short:

HEADLINE: {headline}
CATEGORY: {subcategory}

CRITICAL: Base the script ONLY on this headline. Do NOT invent or hallucinate news events.
Use visual_type "text" for headline-style cards, "image" with image_needed=true for a thematic stock photo.
Requirements:
- Open with the headline as a STRONG HOOK
- Short, punchy sentences
- Add brief context and a "why this matters" beat
- Pattern-interrupt midway with a surprising angle from the headline
- 5-6 segments
- For image segments: image_needed=true, image_query=generic thematic stock photo query (NO movie posters, game art, or promotional stills)""",

    "quiz_riddle": """Create a 45-60 second quiz/riddle video:

RIDDLE: {topic}

Style: dark, suspenseful. Use visual_type "text" for the riddle, "shape" for question marks.
Requirements:
- Open with a STRONG HOOK ("Can you solve this?")
- Present the riddle with building tension
- Pattern-interrupt: dramatic pause before the reveal segment
- Final segment reveals the answer
- 5-6 segments
- Do NOT give away the answer until the last segment""",

    "motivation_content": """Create a 45-60 second original motivational short inspired by the theme: {topic}

Style: warm, uplifting. Use visual_type "text" for key lines.
CRITICAL: Write ORIGINAL motivational words — do NOT quote or attribute real people (no "as X said").
Structure: struggle → turning point → payoff (uplifting arc).
Requirements:
- Open with a STRONG HOOK that resonates emotionally
- Short, punchy sentences with poetic rhythm
- Pattern-interrupt: the turning point moment midway
- End on an empowering payoff
- 5-7 segments""",
}


def _parse_json_response(text: str) -> dict:
    """Extract and parse JSON from Gemini response, tolerating markdown fences."""
    cleaned = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)

    return json.loads(cleaned)


def _validate_script(script: dict, content_type: str) -> dict:
    """Validate and normalize the generated script structure."""
    if "title" not in script or "segments" not in script:
        raise ValueError("Script missing required 'title' or 'segments' fields")

    segments = script["segments"]
    if not segments or len(segments) < 3:
        raise ValueError(f"Script has too few segments: {len(segments)}")

    valid_visual_types = {"text", "number", "list", "shape", "image"}
    for seg in segments:
        if seg.get("visual_type") not in valid_visual_types:
            seg["visual_type"] = "text"
        seg.setdefault("image_needed", False)
        seg.setdefault("image_query", "")
        seg.setdefault("image_path", "")
        seg.setdefault("pause_after", 0.5)

    if content_type == "motivation_content":
        narration = " ".join(s.get("narration", "") for s in segments).lower()
        attribution_patterns = [
            r"\bsaid\b", r"\bas .+ once", r"— \w+", r"- \w+ \w+$",
            r"\bsteve jobs\b", r"\boprah\b", r"\bgandhi\b", r"\bmlk\b",
        ]
        for pattern in attribution_patterns:
            if re.search(pattern, narration):
                logger.warning("Possible attribution detected in motivation script — regenerating recommended")

    return script


def generate_script(content_type: str) -> dict:
    """Generate a structured video script via Gemini for the given content type."""
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"Unknown content type: {content_type}")
    if content_type == "meme_recap":
        raise ValueError("meme_recap uses meme_fetcher, not content_gen")

    api_key = os.getenv(GEMINI_API_KEY_ENV_VAR)
    if not api_key:
        raise ValueError(f"{GEMINI_API_KEY_ENV_VAR} is not set")

    client = genai.Client(api_key=api_key)

    if content_type == "viral_news":
        subcategory, headline = fetch_current_headline()
        prompt_body = CONTENT_PROMPTS["viral_news"].format(
            headline=headline, subcategory=subcategory
        )
    else:
        topic_pool = CONTENT_TOPIC_POOLS.get(content_type, ["general topic"])
        topic = random.choice(topic_pool)
        prompt_body = CONTENT_PROMPTS[content_type].format(topic=topic)

    full_prompt = f"""{prompt_body}

Return ONLY valid JSON matching this schema (no markdown, no commentary):
{SCRIPT_SCHEMA}"""

    logger.info("Generating script for content type: %s", content_type)
    response = client.models.generate_content(
        model=GEMINI_TEXT_MODEL,
        contents=full_prompt,
    )

    script = _parse_json_response(response.text)
    script = _validate_script(script, content_type)
    logger.info("Generated script: %s (%d segments)", script["title"], len(script["segments"]))
    return script
