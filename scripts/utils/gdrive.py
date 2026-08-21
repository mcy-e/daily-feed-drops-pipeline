import io
import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive_service():
    raw = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")
    if not raw:
        logger.warning("GDRIVE_SERVICE_ACCOUNT_JSON not set — Drive unavailable.")
        return None
    try:
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        logger.error("Drive auth failed: %s", exc)
        return None


def list_files(
    service,
    folder_id: str,
    mime_prefix: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not service or not folder_id:
        return []
    q = f"'{folder_id}' in parents and trashed=false"
    if mime_prefix:
        q += f" and mimeType contains '{mime_prefix}'"
    try:
        res = (
            service.files()
            .list(q=q, pageSize=200, fields="files(id,name,mimeType,size)")
            .execute()
        )
        return res.get("files", [])
    except Exception as exc:
        logger.error("list_files failed for folder %s: %s", folder_id, exc)
        return []


def find_file_by_name(
    service,
    folder_ids: List[str],
    filename: str,
) -> Optional[Dict[str, Any]]:
    for fid in folder_ids:
        for f in list_files(service, fid):
            if f["name"] == filename:
                return f
    return None


def download_file(
    service,
    file_id: str,
    dest_path: str,
    max_bytes: Optional[int] = None,
) -> bool:
    try:
        req = service.files().get_media(fileId=file_id)
        with open(dest_path, "wb") as fh:
            dl = MediaIoBaseDownload(fh, req, chunksize=5 * 1024 * 1024)
            done = False
            fetched = 0
            while not done:
                status, done = dl.next_chunk()
                if status:
                    fetched = int(status.resumable_progress or 0)
                if max_bytes and fetched >= max_bytes:
                    logger.info("Hit max_bytes cap (%dMB). Stopping.", max_bytes // 1_048_576)
                    break
        return True
    except Exception as exc:
        logger.error("download_file %s failed: %s", file_id, exc)
        return False


def delete_file(service, file_id: str) -> bool:
    try:
        service.files().delete(fileId=file_id).execute()
        logger.info("Deleted Drive file %s.", file_id)
        return True
    except Exception as exc:
        logger.error("delete_file %s failed: %s", file_id, exc)
        return False


def load_json_file(service, folder_id: str, name: str) -> Optional[dict]:
    files = list_files(service, folder_id)
    target = next((f for f in files if f["name"] == name), None)
    if not target:
        return None
    try:
        req = service.files().get_media(fileId=target["id"])
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
        buf.seek(0)
        return json.loads(buf.read().decode("utf-8"))
    except Exception as exc:
        logger.error("load_json_file %s failed: %s", name, exc)
        return None


def save_json_file(service, folder_id: str, name: str, data: dict) -> bool:
    existing = next((f for f in list_files(service, folder_id) if f["name"] == name), None)
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as tmp:
        json.dump(data, tmp)
        tmp_path = tmp.name
    try:
        media = MediaFileUpload(tmp_path, mimetype="application/json")
        if existing:
            service.files().update(fileId=existing["id"], media_body=media).execute()
        else:
            service.files().create(
                body={"name": name, "parents": [folder_id]},
                media_body=media,
                fields="id",
            ).execute()
        return True
    except Exception as exc:
        logger.error("save_json_file %s failed: %s", name, exc)
        return False
    finally:
        os.unlink(tmp_path)
