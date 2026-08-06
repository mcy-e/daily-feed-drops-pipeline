import json
import logging
import os
import random
import re

from google import genai
import groq as groq_sdk
from openai import OpenAI

from scripts.constants import (
    CONTENT_TOPIC_POOLS,
    CONTENT_TYPES,
    GEMINI_API_KEY_ENV_VAR,
    GEMINI_TEXT_MODEL,
    GROQ_API_KEY_ENV_VAR,
    GROQ_MODEL,
    OPENROUTER_API_KEY_ENV_VAR,
    OPENROUTER_MODEL,
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
    """Extract and parse JSON from a model response, tolerating markdown fences and raw control chars."""
    cleaned = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)
    
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        # Fallback for severe escaping issues: try to strip raw newlines within strings
        cleaned = re.sub(r'([^\\])\n', r'\1\\n', cleaned)
        return json.loads(cleaned, strict=False)


def _validate_script(script: dict, content_type: str) -> dict:
    """Validate and normalize the generated script structure. Raises ValueError if critic rejects it."""
    if "title" not in script or "segments" not in script:
        raise ValueError("CRITIC_REJECT: Script missing required 'title' or 'segments' fields. Return valid JSON.")

    segments = script["segments"]
    if not segments or len(segments) < 3:
        raise ValueError(f"CRITIC_REJECT: Script has too few segments ({len(segments)}). You must generate at least 5 segments.")

    # Critic Check: Religion and NSFW
    banned_words = {"god", "jesus", "allah", "religion", "bible", "quran", "church", "mosque", "sex", "porn", "nude", "nsfw", "kill", "suicide", "murder"}
    full_text = str(script).lower()
    if any(banned in full_text for banned in banned_words):
        raise ValueError("CRITIC_REJECT: Script contains religious, violent, or NSFW terms. Rewrite completely without these topics.")

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
                raise ValueError("CRITIC_REJECT: Motivation script contains attributions to real people. It must be completely original. Rewrite it.")

    return script


def _generate_with_gemini(full_prompt: str) -> str:
    """Call Gemini API and return raw text response."""
    api_key = os.getenv(GEMINI_API_KEY_ENV_VAR)
    if not api_key:
        raise ValueError(f"{GEMINI_API_KEY_ENV_VAR} is not set")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_TEXT_MODEL,
        contents=full_prompt,
    )
    return response.text


def _generate_with_groq(full_prompt: str) -> str:
    """Call Groq API using the official SDK and return raw text response."""
    api_key = os.getenv(GROQ_API_KEY_ENV_VAR)
    if not api_key:
        raise ValueError(f"{GROQ_API_KEY_ENV_VAR} is not set")

    client = groq_sdk.Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.7,
    )
    return completion.choices[0].message.content


def _generate_with_openrouter(full_prompt: str) -> str:
    """Call OpenRouter API via the OpenAI-compatible SDK and return raw text response."""
    api_key = os.getenv(OPENROUTER_API_KEY_ENV_VAR)
    if not api_key:
        raise ValueError(f"{OPENROUTER_API_KEY_ENV_VAR} is not set")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    completion = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.7,
    )
    return completion.choices[0].message.content


_PROVIDER_CHAIN = [
    ("Gemini", _generate_with_gemini),
    ("Groq", _generate_with_groq),
    ("OpenRouter", _generate_with_openrouter),
]

_QUOTA_ERRORS = (
    "quota", "rate", "limit", "429", "resource exhausted",
    "too many requests", "insufficient_quota",
)


def _is_quota_error(exc: Exception) -> bool:
    """Return True if the exception looks like a quota or rate-limit error."""
    msg = str(exc).lower()
    return any(kw in msg for kw in _QUOTA_ERRORS)


def generate_script(content_type: str) -> dict:
    """Generate a structured video script via LLM with self-correction and fallback."""
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"Unknown content type: {content_type}")
    if content_type == "meme_recap":
        raise ValueError("meme_recap uses meme_fetcher, not content_gen")

    if content_type == "viral_news":
        subcategory, headline = fetch_current_headline()
        prompt_body = CONTENT_PROMPTS["viral_news"].format(
            headline=headline, subcategory=subcategory
        )
    else:
        topic_pool = CONTENT_TOPIC_POOLS.get(content_type, ["general topic"])
        topic = random.choice(topic_pool)
        prompt_body = CONTENT_PROMPTS[content_type].format(topic=topic)

    base_prompt = f"""{prompt_body}

Return ONLY valid JSON matching this schema (no markdown, no commentary):
{SCRIPT_SCHEMA}"""

    logger.info("Generating script for content type: %s", content_type)

    last_exc = None
    for provider_name, provider_fn in _PROVIDER_CHAIN:
        prompt_to_send = base_prompt
        # Up to 2 self-correction attempts per provider
        for attempt in range(3):
            try:
                logger.info("Trying provider: %s (Attempt %d/3)", provider_name, attempt + 1)
                raw = provider_fn(prompt_to_send)
                script = _parse_json_response(raw)
                script = _validate_script(script, content_type)
                script["provider"] = provider_name
                logger.info("Script generated via %s: '%s' (%d segments)", provider_name, script["title"], len(script["segments"]))
                return script
            except ValueError as exc:
                if str(exc).startswith("CRITIC_REJECT:"):
                    logger.warning("LLM Critic rejected script: %s. Attempting self-correction...", exc)
                    prompt_to_send = f"{base_prompt}\n\nWARNING: Your last output failed validation with this error:\n{exc}\n\nFIX THIS ERROR AND RETURN VALID JSON."
                    last_exc = exc
                    continue
                else:
                    # Normal value error (like json decode)
                    last_exc = exc
                    break
            except genai.errors.APIError as exc:
                last_exc = exc
                if getattr(exc, 'code', None) == 429 or _is_quota_error(exc):
                    logger.warning("Provider %s hit quota/rate-limit: %s — trying next", provider_name, type(exc).__name__)
                    break
                else:
                    logger.warning("Provider %s failed: %s — aborting fallback chain", provider_name, type(exc).__name__)
                    raise
            except Exception as exc:
                last_exc = exc
                if _is_quota_error(exc):
                    logger.warning("Provider %s hit quota/rate-limit: %s — trying next", provider_name, type(exc).__name__)
                    break
                else:
                    logger.warning("Provider %s failed: %s — aborting fallback chain", provider_name, type(exc).__name__)
                    raise

    raise RuntimeError(
        f"All LLM providers failed for content type '{content_type}'. Last error: {last_exc}"
    ) from last_exc
