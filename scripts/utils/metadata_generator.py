import logging
import os

logger = logging.getLogger(__name__)

# First hashtag is always #Shorts — YouTube requires it for classification
_SHORTS_TAG = "#Shorts"

# Rotating pool of evergreen tags that help with discoverability
_EVERGREEN_POOL = [
    "#meme", "#memes", "#funnyvideos", "#comedy", "#viral",
    "#gaming", "#relatable", "#trending", "#darkhumor", "#lol",
    "#dankmemes", "#memesdaily", "#funnymemes", "#humor", "#viralshorts",
]

_SYSTEM_PROMPT = (
    "You are a YouTube Shorts metadata writer. "
    "Given a meme title, return ONLY a JSON object with two fields:\n"
    '  "description": a single punchy sentence (max 120 chars) that describes or reacts to the meme. '
    "Be witty, keep dark humor if the meme calls for it. Do NOT add hashtags here.\n"
    '  "hashtags": a list of exactly 4 hashtag strings (include the # symbol) that match the meme\'s theme. '
    "Pick specific tags that will help the video trend. Do NOT include #Shorts — it is added separately.\n"
    "Respond with raw JSON only. No markdown, no explanation."
)


def _call_gemini(meme_title: str) -> dict | None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            f"{_SYSTEM_PROMPT}\n\nMeme title: {meme_title}"
        )
        import json
        return json.loads(response.text.strip())
    except Exception as exc:
        logger.warning("Gemini metadata generation failed: %s", exc)
        return None


def _call_groq(meme_title: str) -> dict | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    try:
        import json
        from groq import Groq

        client = Groq(api_key=api_key)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Meme title: {meme_title}"},
            ],
            model="llama3-8b-8192",
            temperature=0.9,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        raw = chat_completion.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Groq metadata generation failed: %s", exc)
        return None


def _local_fallback(meme_title: str) -> dict:
    import random

    words = [w.strip(".,!?\"'").lower() for w in meme_title.split() if len(w) > 4]
    title_tags = [f"#{w}" for w in words[:2] if w.isalpha()]
    extra = random.sample(_EVERGREEN_POOL, min(4 - len(title_tags), len(_EVERGREEN_POOL)))
    hashtags = (title_tags + extra)[:4]

    return {
        "description": f"When the meme hits different... {meme_title[:80]}",
        "hashtags": hashtags,
    }


def generate_youtube_metadata(meme_title: str) -> dict:
    """Generate a unique description and hashtag list for a YouTube Short.

    Tries Gemini first, then Groq, then falls back to a local generator.
    Always returns a dict with 'description' (str) and 'hashtags' (list[str]).
    The #Shorts tag is always prepended to the hashtag list.
    """
    result = _call_gemini(meme_title) or _call_groq(meme_title) or _local_fallback(meme_title)

    # Normalize: ensure exactly 4 non-Shorts hashtags
    hashtags = [h if h.startswith("#") else f"#{h}" for h in result.get("hashtags", [])]
    hashtags = [h for h in hashtags if h.lower() != "#shorts"][:4]

    if len(hashtags) < 4:
        import random
        needed = 4 - len(hashtags)
        hashtags += random.sample(_EVERGREEN_POOL, min(needed, len(_EVERGREEN_POOL)))

    return {
        "description": result.get("description", f"{meme_title[:80]}"),
        "hashtags": [_SHORTS_TAG] + hashtags,
    }
