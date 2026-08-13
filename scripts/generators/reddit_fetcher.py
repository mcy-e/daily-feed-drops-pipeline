import logging
import pathlib
import random
import uuid
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

REDDIT_HEADERS = {"User-Agent": "DailyFeedDrops/1.0 (content bot)"}

SUBREDDITS = {
    "dark_facts": [
        "r/Damnthatsinteresting",
        "r/todayilearned",
        "r/interestingasfuck",
        "r/Mindblown",
    ],
    "shower_thoughts": [
        "r/Showerthoughts",
        "r/Lightbulb",
        "r/LifeProTips",
    ],
}


def _fetch_reddit_posts(subreddit: str, limit: int = 25) -> list[dict]:
    url = f"https://www.reddit.com/{subreddit}/hot.json?limit={limit}"
    try:
        resp = requests.get(url, headers=REDDIT_HEADERS, timeout=10, verify=False)
        resp.raise_for_status()
        posts = resp.json()["data"]["children"]
        return [p["data"] for p in posts if not p["data"].get("stickied")]
    except Exception as exc:
        logger.warning("Reddit fetch failed for %s: %s", subreddit, exc)
        return []


def _clean_text(text: str) -> str:
    text = text.strip()
    if len(text) > 220:
        text = text[:217] + "..."
    return text


def fetch_reddit_script(content_type: str) -> dict | None:
    subreddits = SUBREDDITS.get(content_type, [])
    if not subreddits:
        return None

    random.shuffle(subreddits)
    all_posts = []
    for sub in subreddits:
        all_posts.extend(_fetch_reddit_posts(sub))
        if len(all_posts) >= 10:
            break

    if not all_posts:
        logger.error("No Reddit posts found for %s", content_type)
        return None

    # Filter posts based on banned words and NSFW tags
    banned_words = {"sex", "porn", "nude", "nsfw", "suicide", "murder", "kill", "rape", "death", "politics", "religion", "god", "jesus"}
    valid_posts = []
    for p in all_posts:
        if p.get("over_18") or p.get("is_video"):
            continue
        title_lower = p.get("title", "").lower()
        if not any(banned in title_lower for banned in banned_words):
            valid_posts.append(p)

    if not valid_posts:
        logger.error("No valid Reddit posts found for %s after filtering", content_type)
        return _get_fallback_script(content_type)

    # Pick a high-scoring post
    scored = sorted(valid_posts, key=lambda p: p.get("score", 0), reverse=True)
    post = scored[0] if scored else random.choice(valid_posts)

    title = _clean_text(post.get("title", ""))
    if not title:
        return _get_fallback_script(content_type)

    # Try to grab the post image if it's a direct image link
    image_url = None
    url = post.get("url", "")
    if url and any(url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif")):
        image_url = url
    elif post.get("thumbnail") and post["thumbnail"].startswith("http"):
        image_url = post["thumbnail"]

    DESCRIPTIONS = {
        "dark_facts": f"Mind-blowing fact: {title} 🤯 #darkfacts #mindblow #facts #shorts",
        "shower_thoughts": f"This will break your brain 🚿💭 {title} #showerthoughts #deepthoughts #mindblown #shorts",
    }

    TAGS = {
        "dark_facts": ["darkfacts", "mindblowing", "facts", "didyouknow", "shorts"],
        "shower_thoughts": ["showerthoughts", "deepthoughts", "mindblown", "philosophical", "shorts"],
    }

    segment = {
        "id": 1,
        "narration": title,
        "visual_type": "image",
        "visual_content": title,
        "image_needed": True,
    }

    if image_url:
        segment["reddit_image_url"] = image_url

    return {
        "title": title[:80],
        "description": DESCRIPTIONS.get(content_type, title),
        "tags": TAGS.get(content_type, ["shorts"]),
        "segments": [segment],
    }

def _get_fallback_script(content_type: str) -> dict:
    if content_type == "dark_facts":
        text = "Did you know that bananas are slightly radioactive? Eating 10,000 at once could be lethal."
    else:
        text = "Water is just a potion that cures exhaustion but gives you a debuff that makes you need to pee."
        
    return {
        "title": "Interesting Fact",
        "description": "Mind blown! #shorts #mindblown",
        "tags": ["shorts", "mindblown"],
        "segments": [{
            "id": 1,
            "narration": text,
            "visual_type": "image",
            "visual_content": text,
            "image_needed": True
        }]
    }