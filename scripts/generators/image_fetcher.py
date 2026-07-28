import logging
import os
import pathlib
import uuid

import requests

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from scripts.constants import PEXELS_API_KEY_ENV_VAR, PEXELS_SEARCH_URL
from scripts.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def fetch_pexels_image(query: str, dest_dir: pathlib.Path) -> str:
    """Download a thematic stock photo from Pexels. Returns local image path."""
    api_key = os.getenv(PEXELS_API_KEY_ENV_VAR)
    if not api_key:
        raise ValueError(f"{PEXELS_API_KEY_ENV_VAR} is not set")

    dest_dir.mkdir(parents=True, exist_ok=True)

    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 15, "orientation": "portrait"}

    logger.info("Searching Pexels for: %s", query)
    resp = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params, timeout=30, verify=False)
    resp.raise_for_status()
    photos = resp.json().get("photos", [])

    if not photos:
        raise RuntimeError(f"No Pexels results for query: {query}")

    photo = photos[0]
    image_url = photo["src"].get("large2x") or photo["src"].get("large") or photo["src"]["original"]

    filename = f"pexels_{uuid.uuid4().hex[:8]}.jpg"
    dest_path = dest_dir / filename
    logger.info("Downloading Pexels image from %s", image_url)
    img_resp = requests.get(image_url, timeout=60, verify=False)
    img_resp.raise_for_status()
    dest_path.write_bytes(img_resp.content)

    logger.info("Downloaded Pexels image to %s", dest_path)
    return str(dest_path)
