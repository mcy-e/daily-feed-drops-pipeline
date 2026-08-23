import logging
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from scripts.auth.google_auth import get_credentials
from scripts.constants import YOUTUBE_PRIVACY_STATUS_ENV_VAR
from scripts.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def upload_video(
    video_path: str,
    title: str,
    description: str,
    privacy_status: str = None,
    tags: list = None,
    category_id: str = "22",
) -> str:
    """Uploads a video to YouTube and returns the video URL."""
    if privacy_status is None:
        privacy_status = os.getenv(YOUTUBE_PRIVACY_STATUS_ENV_VAR, "private")
    if tags is None:
        tags = ["football", "highlights", "shorts", "soccer"]
    
    logger.info("Starting YouTube upload for %s (Status: %s)", video_path, privacy_status)
    credentials = get_credentials()
    youtube = build("youtube", "v3", credentials=credentials)

    # YouTube requires #Shorts in the title to classify the video as a Short
    if "#Shorts" not in title and "#shorts" not in title:
        title = f"{title} #Shorts"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False
        }
    }

    try:
        insert_request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True)
        )
        response = insert_request.execute()
        
        video_id = response.get("id")
        url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("Upload complete: %s", url)
        return url
        
    except Exception as exc:
        logger.error("YouTube upload failed: %s", exc)
        raise RuntimeError(f"YouTube upload failed: {exc}") from exc
