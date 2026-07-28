import logging
import os
import requests
import urllib3
from scripts.constants import TELEGRAM_BOT_TOKEN_ENV_VAR, TELEGRAM_CHAT_ID_ENV_VAR

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

def send_message(text: str):
    """Send a Telegram notification."""
    bot_token = os.getenv(TELEGRAM_BOT_TOKEN_ENV_VAR)
    chat_id = os.getenv(TELEGRAM_CHAT_ID_ENV_VAR)

    if not bot_token or not chat_id:
        logger.warning("Telegram credentials not configured. Skipping notification.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        resp = requests.post(url, json=payload, timeout=10, verify=False)
        resp.raise_for_status()
        logger.info("Telegram notification sent successfully.")
    except Exception as exc:
        logger.error("Failed to send Telegram notification: %s", exc)

def send_video(video_path: str, caption: str):
    """Send a video to Telegram with a caption."""
    bot_token = os.getenv(TELEGRAM_BOT_TOKEN_ENV_VAR)
    chat_id = os.getenv(TELEGRAM_CHAT_ID_ENV_VAR)

    if not bot_token or not chat_id:
        logger.warning("Telegram credentials not configured. Skipping video notification.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    
    try:
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'}
            resp = requests.post(url, data=data, files=files, timeout=60, verify=False)
            resp.raise_for_status()
            logger.info("Telegram video sent successfully.")
    except Exception as exc:
        logger.error("Failed to send Telegram video: %s", exc)
