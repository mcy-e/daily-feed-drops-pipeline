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
    """Fetch a real current headline from GNews.
    Tries random subcategories until one works.

    Returns (subcategory_key, headline_text).
    """
    api_key = os.getenv(GNEWS_API_KEY_ENV_VAR)
    if not api_key:
        raise ValueError(f"{GNEWS_API_KEY_ENV_VAR} is not set")

    subcategories = list(VIRAL_NEWS_SUBCATEGORIES.keys())
    random.shuffle(subcategories)

    for subcategory in subcategories:
        query = VIRAL_NEWS_SUBCATEGORIES[subcategory]
        params = {
            "q": query,
            "lang": "en",
            "max": 10,
            "apikey": api_key,
        }

        logger.info("Fetching GNews headline for sub-category: %s", subcategory)
        try:
            resp = requests.get(GNEWS_SEARCH_URL, params=params, timeout=30, verify=False)
            resp.raise_for_status()
            data = resp.json()

            articles = data.get("articles", [])
            if not articles:
                logger.warning(f"No GNews articles returned for query: {query}. Trying another...")
                continue

            article = random.choice(articles)
            headline = article.get("title", "").strip()
            if not headline:
                logger.warning("GNews article had empty title. Trying another...")
                continue

            logger.info("Selected headline: %s", headline)
            return subcategory, headline
        except Exception as e:
            logger.warning(f"Failed to fetch for {subcategory}: {e}. Trying another...")
            continue
            
    raise RuntimeError("No GNews articles returned for any subcategory query.")
