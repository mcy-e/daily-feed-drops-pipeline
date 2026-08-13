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
        "r/UnbelievableStuff",
        "r/Weird",
        "r/mildlyinteresting",
        "r/OutOfTheLoop",
        "r/theydidthemath",
        "r/science",
        "r/history",
        "r/Natureisfuckinglit",
        "r/woahdude",
        "r/educationalgifs",
    ],
    "shower_thoughts": [
        "r/Showerthoughts",
        "r/Lightbulb",
        "r/LifeProTips",
        "r/philosophy",
        "r/RandomThoughts",
        "r/DoesAnybodyElse",
        "r/Existential_crisis",
        "r/mildlyinteresting",
        "r/CrazyIdeas",
        "r/self",
        "r/introspection",
        "r/AskReddit",
    ],
}

# Only block truly toxic/explicit content — not words that appear in normal facts
BANNED_WORDS = {
    "sex", "porn", "nude", "nsfw", "rape", "pedophile",
    "politics", "election", "democrat", "republican", "trump", "biden",
    "religion", "jesus", "allah", "god", "church",
    "suicide", "self-harm",
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

    # Shuffle and try all subreddits until we collect enough posts
    shuffled = list(subreddits)
    random.shuffle(shuffled)
    all_posts = []

    for sub in shuffled:
        posts = _fetch_reddit_posts(sub)
        all_posts.extend(posts)
        if len(all_posts) >= 20:
            break

    if not all_posts:
        logger.warning("All Reddit sources failed for %s — using hardcoded fallback", content_type)
        return _get_fallback_script(content_type)

    valid_posts = []
    for p in all_posts:
        if p.get("over_18") or p.get("is_video"):
            continue
        title_lower = p.get("title", "").lower()
        if not any(banned in title_lower for banned in BANNED_WORDS):
            valid_posts.append(p)

    if not valid_posts:
        logger.warning("All posts filtered for %s — using hardcoded fallback", content_type)
        return _get_fallback_script(content_type)

    # Pick top scoring post
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

FALLBACK_DARK_FACTS = [
    "A day on Venus is longer than a year on Venus. It rotates so slowly that the Sun rises only once every 243 Earth days.",
    "There are more possible iterations of a game of chess than there are atoms in the observable universe.",
    "Cleopatra lived closer in time to the Moon landing than to the construction of the Great Pyramid.",
    "Oxford University is older than the Aztec Empire. Teaching began there around 1096 AD.",
    "The average cloud weighs about 1.1 million pounds — yet it floats because the water droplets are spread over a huge area.",
    "If you removed all the empty space from atoms in the human body, all 7 billion people on Earth would fit into an apple.",
    "Woolly mammoths were still alive when the Great Pyramid of Giza was being built.",
    "Sharks are older than trees. Sharks have existed for around 450 million years, trees only about 360 million.",
    "There are more trees on Earth than stars in the Milky Way galaxy.",
    "Honey never spoils. Archaeologists have found 3,000-year-old honey in Egyptian tombs that was still edible.",
]

FALLBACK_SHOWER_THOUGHTS = [
    "Your future self is a complete stranger who will have to deal with every decision you make today.",
    "The word 'bed' actually looks like a bed.",
    "When you're a kid, you don't realize you're also watching your parents be kids for the very first time.",
    "You can't hum while holding your nose closed. Go ahead. Try it.",
    "Every time you shuffle a deck of cards, the order has almost certainly never existed before in history.",
    "Somewhere right now, someone is hearing their favorite song for the very first time.",
    "Nothing is on fire. Fire is on things.",
    "The brain named itself.",
    "At some point, your parents put you down and never picked you up again.",
    "Whoever invented the clock had to decide what time it was first.",
]

def _get_fallback_script(content_type: str) -> dict:
    if content_type == "dark_facts":
        text = random.choice(FALLBACK_DARK_FACTS)
        description = f"Mind-blowing fact 🤯 {text[:80]}... #darkfacts #didyouknow #shorts"
        tags = ["darkfacts", "mindblowing", "facts", "didyouknow", "shorts"]
        title = "Dark Fact of the Day"
    else:
        text = random.choice(FALLBACK_SHOWER_THOUGHTS)
        description = f"This will break your brain 🚿💭 {text[:80]}... #showerthoughts #shorts"
        tags = ["showerthoughts", "deepthoughts", "mindblown", "shorts"]
        title = "Shower Thought of the Day"

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "segments": [{
            "id": 1,
            "narration": text,
            "visual_type": "image",
            "visual_content": text,
            "image_needed": True
        }]
    }