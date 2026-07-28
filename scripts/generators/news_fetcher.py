import logging
import os
import random

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from scripts.constants import GNEWS_API_KEY_ENV_VAR, GNEWS_SEARCH_URL, VIRAL_NEWS_SUBCATEGORIES
from scripts.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def fetch_current_headline() -> tuple[str, str]:
    """Fetch a real current headline from GNews for a random sub-category.

    Returns (subcategory_key, headline_text).
    """
    api_key = os.getenv(GNEWS_API_KEY_ENV_VAR)
    if not api_key:
        raise ValueError(f"{GNEWS_API_KEY_ENV_VAR} is not set")

    subcategory = random.choice(list(VIRAL_NEWS_SUBCATEGORIES.keys()))
    query = VIRAL_NEWS_SUBCATEGORIES[subcategory]

    params = {
        "q": query,
        "lang": "en",
        "max": 10,
        "apikey": api_key,
    }

    logger.info("Fetching GNews headline for sub-category: %s", subcategory)
    resp = requests.get(GNEWS_SEARCH_URL, params=params, timeout=30, verify=False)
    resp.raise_for_status()
    data = resp.json()

    articles = data.get("articles", [])
    if not articles:
        raise RuntimeError(f"No GNews articles returned for query: {query}")

    article = random.choice(articles)
    headline = article.get("title", "").strip()
    if not headline:
        raise RuntimeError("GNews article had empty title")

    logger.info("Selected headline: %s", headline)
    return subcategory, headline
