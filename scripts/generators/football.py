import io
import logging
import pathlib
import random

from googleapiclient.http import MediaIoBaseDownload

from scripts.auth.google_auth import build_drive_service, get_credentials
from scripts.constants import (
    ALLOWED_VIDEO_EXTENSIONS,
    DEFAULT_DOWNLOAD_DIR,
    VIDEO_MIME_QUERY,
)
from scripts.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


def get_service():
    """Authenticate via shared OAuth and return a Drive service."""
    credentials = get_credentials()
    return build_drive_service(credentials)


@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def list_files(service, folder_id: str) -> list[dict]:
    """List video files inside a Drive folder, paginating through all results."""
    query = f"'{folder_id}' in parents and trashed = false and {VIDEO_MIME_QUERY}"
    all_files = []
    page_token = None

    try:
        while True:
            response = (
                service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageToken=page_token,
                    pageSize=100,
                )
                .execute()
            )

            files = response.get("files", [])
            filtered = [
                f
                for f in files
                if pathlib.PurePosixPath(f["name"]).suffix.lower()
                in ALLOWED_VIDEO_EXTENSIONS
            ]
            all_files.extend(filtered)
            logger.info(
                "Fetched %d files (page), %d after extension filter",
                len(files),
                len(filtered),
            )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    except Exception as exc:
        logger.error("Failed to list files in folder %s: %s", folder_id, exc)
        raise RuntimeError(
            f"Drive API list failed for folder {folder_id}: {exc}"
        ) from exc

    logger.info("Total video files found: %d", len(all_files))
    return all_files


def pick_random_file(service, folder_id: str) -> dict:
    """Pick one random video file from a Drive folder."""
    files = list_files(service, folder_id)

    if not files:
        raise FileNotFoundError(
            f"No video files found in Drive folder: {folder_id}"
        )

    chosen = random.choice(files)
    logger.info("Picked file: %s (id=%s)", chosen["name"], chosen["id"])
    return chosen


def pick_weighted_subfolder(service, subfolder_config: dict) -> dict:
    """
    Pick a subfolder based on weights, then pick a random file inside it.
    If the chosen subfolder is empty, skip it and choose another one.
    """
    available_folders = dict(subfolder_config)

    while available_folders:
        names = list(available_folders.keys())
        weights = [available_folders[n].get("weight", 0) for n in names]
        
        if sum(weights) <= 0:
            break

        chosen_name = random.choices(names, weights=weights, k=1)[0]
        chosen_id = available_folders[chosen_name]["id"]
        
        logger.info("Weighted picker chose subfolder: %s (id=%s)", chosen_name, chosen_id)
        
        files = list_files(service, chosen_id)
        if files:
            chosen = random.choice(files)
            chosen['content_mode'] = available_folders[chosen_name].get('content_mode', 'highlight')
            chosen['_folder_id'] = chosen_id
            logger.info("Picked file: %s (id=%s) from %s (mode: %s)", chosen["name"], chosen["id"], chosen_name, chosen['content_mode'])
            return chosen
        else:
            logger.warning("Subfolder '%s' is empty. Removing from choices and retrying.", chosen_name)
            del available_folders[chosen_name]

    raise FileNotFoundError("All configured subfolders are empty or have 0 weight.")


@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def find_companion_json(
    service,
    folder_id: str,
    video_filename: str,
    dest_dir: str | pathlib.Path = DEFAULT_DOWNLOAD_DIR,
) -> str | None:
    """
    Check for a companion JSON file in the same Drive folder.
    Expected name: {video_stem}.json. Downloads it read-only if found.
    Returns local path or None.
    """
    video_stem = pathlib.PurePosixPath(video_filename).stem
    json_name = f"{video_stem}.json"
    query = f"name = '{json_name}' and '{folder_id}' in parents and trashed = false"

    try:
        response = (
            service.files()
            .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
            .execute()
        )
        files = response.get("files", [])
        if not files:
            logger.info("No companion JSON found for '%s'", video_filename)
            return None

        json_meta = files[0]
        logger.info("Found companion JSON: %s (id=%s)", json_meta["name"], json_meta["id"])

        dest_dir = pathlib.Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{json_meta['id']}.json"
        dest_path = dest_dir / safe_name

        request = service.files().get_media(fileId=json_meta["id"])
        with open(dest_path, "wb") as fh:
            from googleapiclient.http import MediaIoBaseDownload
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        logger.info("Downloaded companion JSON to %s", dest_path)
        return str(dest_path)

    except Exception as exc:
        logger.error("Failed to fetch companion JSON for '%s': %s", video_filename, exc)
        return None


@retry_with_backoff(max_retries=3, delays=(2, 5, 10))
def download_file(
    service,
    file_meta: dict,
    dest_dir: str | pathlib.Path = DEFAULT_DOWNLOAD_DIR,
) -> str:
    """Download a Drive file to a local directory. Returns the local path."""
    dest_dir = pathlib.Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Use file ID for filename to prevent spaces/special chars from breaking ffmpeg
    import pathlib as std_pathlib
    ext = std_pathlib.PurePosixPath(file_meta["name"]).suffix.lower()
    safe_name = f"{file_meta['id']}{ext}"
    dest_path = dest_dir / safe_name

    try:
        request = service.files().get_media(fileId=file_meta["id"])
        with open(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.info(
                        "Download progress: %d%%",
                        int(status.progress() * 100),
                    )

        logger.info("Downloaded %s to %s", file_meta["name"], dest_path)
        return str(dest_path)

    except Exception as exc:
        logger.error("Failed to download file %s: %s", file_meta["name"], exc)
        raise RuntimeError(
            f"Drive download failed for {file_meta['name']}: {exc}"
        ) from exc
