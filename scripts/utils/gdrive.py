import os
import json
import logging
from typing import List, Dict, Any, Optional
import io
import tempfile

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """Authenticate and return the Google Drive service."""
    creds_json_str = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")
    if not creds_json_str:
        logger.warning("GDRIVE_SERVICE_ACCOUNT_JSON environment variable not set.")
        return None
        
    try:
        creds_dict = json.loads(creds_json_str)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        return service
    except Exception as e:
        logger.error(f"Failed to authenticate with Google Drive: {e}")
        return None

def list_files_in_folder(service, folder_id: str, mime_type_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all files in a specific Google Drive folder."""
    if not service or not folder_id:
        return []
        
    query = f"'{folder_id}' in parents and trashed = false"
    if mime_type_prefix:
        query += f" and mimeType contains '{mime_type_prefix}'"
        
    try:
        results = service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, size)"
        ).execute()
        items = results.get('files', [])
        return items
    except Exception as e:
        logger.error(f"Error listing files in folder {folder_id}: {e}")
        return []

def download_file(service, file_id: str, destination_path: str) -> bool:
    """Download a file from Google Drive to the local filesystem."""
    if not service or not file_id:
        return False
        
    try:
        request = service.files().get_media(fileId=file_id)
        with open(destination_path, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
        return True
    except Exception as e:
        logger.error(f"Error downloading file {file_id}: {e}")
        return False

def delete_file(service, file_id: str) -> bool:
    """Delete a file from Google Drive."""
    if not service or not file_id:
        return False
        
    try:
        service.files().delete(fileId=file_id).execute()
        logger.info(f"Successfully deleted file {file_id} from Google Drive.")
        return True
    except Exception as e:
        logger.error(f"Error deleting file {file_id}: {e}")
        return False

def upload_json_file(service, folder_id: str, file_name: str, data: dict) -> str:
    """Upload or update a JSON file in Google Drive."""
    if not service:
        return None
        
    query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
    try:
        results = service.files().list(q=query, fields="files(id)").execute()
        items = results.get('files', [])
        
        # Write dict to temporary file for upload
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as temp:
            json.dump(data, temp)
            temp_path = temp.name
            
        media = MediaFileUpload(temp_path, mimetype='application/json', resumable=True)
        
        if items:
            # Update existing
            file_id = items[0]['id']
            service.files().update(fileId=file_id, media_body=media).execute()
            os.unlink(temp_path)
            return file_id
        else:
            # Create new
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            os.unlink(temp_path)
            return file.get('id')
    except Exception as e:
        logger.error(f"Error uploading json file {file_name}: {e}")
        return None

def download_json_file(service, folder_id: str, file_name: str) -> Optional[dict]:
    """Download a JSON file from Google Drive and return its parsed dict."""
    if not service:
        return None
        
    query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
    try:
        results = service.files().list(q=query, fields="files(id)").execute()
        items = results.get('files', [])
        
        if not items:
            return None
            
        file_id = items[0]['id']
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            
        fh.seek(0)
        return json.loads(fh.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Error downloading json file {file_name}: {e}")
        return None
