import json
import logging
import pathlib
import random

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_SUBREDDITS = ["TwoSentenceHorror", "3amjokes", "dadjokes"]

_BANNED = {"porn", "nude", "nsfw", "rape", "cp", "suicide", "selfharm"}

_HEADERS = {"User-Agent": "DailyFeedDrops/2.0"}

_TARGET_COUNT = 15
_REQUEST_LIMIT = 50
_BANK_PATH = pathlib.Path(__file__).parent.parent / "data" / "cursed_bank.json"


def _is_safe(title: str, body: str, nsfw: bool, spoiler: bool) -> bool:
    if nsfw or spoiler:
        return False
    combined = (title + " " + body).lower()
    return not any(b in combined for b in _BANNED)


def _posts_from_pullpush(sub: str) -> list[dict]:
    """Fetch text-based posts directly from PullPush archive to bypass Reddit blocks."""
    try:
        r = requests.get(
            f"https://api.pullpush.io/reddit/search/submission/?subreddit={sub}&sort=desc&sort_type=score&size={_REQUEST_LIMIT}",
            headers=_HEADERS,
            timeout=15,
            verify=False,
        )
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as exc:
        logger.debug("PullPush posts failed for r/%s: %s", sub, exc)
    return []


def _fetch_from_subreddit(sub: str) -> list[dict]:
    results = []

    # Pull from the public archive to completely bypass Reddit API limits/blocks
    posts = _posts_from_pullpush(sub)

    for d in posts:
        title = d.get("title", "").strip()
        body = d.get("selftext", "").strip()
        
        # Must have both a setup (title) and a punchline (body)
        if not title or not body or body in ("[deleted]", "[removed]"):
            continue
            
        if not _is_safe(title, body, d.get("over_18", False), d.get("spoiler", False)):
            continue
            
        post_id = d.get("id", "")
        if not post_id:
            continue
            
        results.append({
            "setup": title[:200],
            "punchline": body[:300],
            "image_url": None,
            "post_id": post_id,
            "subreddit": sub,
        })
        if len(results) >= 5:
            break

    return results


def _fetch_from_bank() -> list[dict]:
    """Load items from the local content bank when all network sources fail."""
    try:
        with open(_BANK_PATH, "r", encoding="utf-8-sig") as f:
            bank = json.load(f)
        items = [
            {
                "setup": entry["setup"],
                "punchline": entry["punchline"],
                "image_url": None,
                "post_id": f"bank_{i}",
                "subreddit": "bank",
            }
            for i, entry in enumerate(bank)
        ]
        random.shuffle(items)
        logger.info("Loaded %d items from local content bank", len(items))
        return items
    except Exception as exc:
        logger.error("Failed to load local content bank: %s", exc)
        return []


def fetch_cursed_items() -> list[dict]:
    """Fetch cursed posts with setup+punchline.

    Priority: Reddit → PullPush fallback → local content bank.
    The local bank guarantees the pipeline never aborts from network failure.
    """
    all_items = []
    shuffled = list(_SUBREDDITS)
    random.shuffle(shuffled)
    for sub in shuffled:
        items = _fetch_from_subreddit(sub)
        all_items.extend(items)
        logger.info("Fetched %d items from r/%s", len(items), sub)
        if len(all_items) >= _TARGET_COUNT:
            break

    if not all_items:
        logger.warning("All network sources returned 0 items — using local content bank")
        all_items = _fetch_from_bank()

    random.shuffle(all_items)
    logger.info("Total cursed items fetched: %d", len(all_items))
    return all_items[:_TARGET_COUNT]
