import logging
import random
import uuid

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_SUBREDDITS = ["cursedcomments", "HolUp", "clevercomebacks", "facepalm"]

_BANNED = {"porn", "nude", "nsfw", "rape", "cp", "suicide", "selfharm"}

_HEADERS = {"User-Agent": "DailyFeedDrops/2.0"}

_TARGET_COUNT = 15
_REQUEST_LIMIT = 30


def _is_safe(title: str, nsfw: bool, spoiler: bool) -> bool:
    if nsfw or spoiler:
        return False
    tl = title.lower()
    return not any(b in tl for b in _BANNED)


def _fetch_top_comment(sub: str, post_id: str) -> str | None:
    url = f"https://api.pullpush.io/reddit/search/comment/?link_id={post_id}&sort=desc&sort_type=score&size=5"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15, verify=False)
        r.raise_for_status()
        data = r.json()
        comments = data.get("data", [])
        for comment in comments:
            body = comment.get("body", "").strip()
            if body and body not in ("[deleted]", "[removed]") and len(body) > 5:
                return body[:300]
    except Exception as exc:
        logger.debug("Comment fetch failed for %s/%s: %s", sub, post_id, exc)
    return None


def _fetch_from_subreddit(sub: str) -> list[dict]:
    results = []
    try:
        r = requests.get(
            f"https://api.pullpush.io/reddit/search/submission/?subreddit={sub}&sort=desc&sort_type=score&size={_REQUEST_LIMIT}",
            headers=_HEADERS,
            timeout=15,
            verify=False,
        )
        r.raise_for_status()
        posts = r.json().get("data", [])
        for d in posts:
            title = d.get("title", "")
            if not _is_safe(title, d.get("over_18", False), d.get("spoiler", False)):
                continue
            post_id = d.get("id", "")
            if not post_id:
                continue
            punchline = _fetch_top_comment(sub, post_id)
            if not punchline:
                continue
            url = d.get("url", "")
            image_url = url if url.lower().endswith((".jpg", ".jpeg", ".png")) else None
            results.append({
                "setup": title[:200],
                "punchline": punchline,
                "image_url": image_url,
                "post_id": post_id,
                "subreddit": sub,
            })
            if len(results) >= 5:
                break
    except Exception as exc:
        logger.warning("Subreddit r/%s fetch failed: %s", sub, exc)
    return results


def fetch_cursed_items() -> list[dict]:
    """Fetch cursed posts with setup+punchline across configured subreddits."""
    all_items = []
    shuffled = list(_SUBREDDITS)
    random.shuffle(shuffled)
    for sub in shuffled:
        items = _fetch_from_subreddit(sub)
        all_items.extend(items)
        logger.info("Fetched %d items from r/%s", len(items), sub)
        if len(all_items) >= _TARGET_COUNT:
            break
    random.shuffle(all_items)
    logger.info("Total cursed items fetched: %d", len(all_items))
    return all_items[:_TARGET_COUNT]
