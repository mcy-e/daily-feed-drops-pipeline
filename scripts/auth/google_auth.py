import logging
import pathlib

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from scripts.constants import (
    DEFAULT_CLIENT_SECRET_PATH,
    DEFAULT_TOKEN_PATH,
    DRIVE_READONLY_SCOPES,
)

logger = logging.getLogger(__name__)


def get_credentials(
    client_secret_path: str | pathlib.Path = DEFAULT_CLIENT_SECRET_PATH,
    token_path: str | pathlib.Path = DEFAULT_TOKEN_PATH,
    scopes: list[str] = None,
) -> Credentials:
    """Load cached credentials or run the OAuth consent flow."""
    if scopes is None:
        scopes = DRIVE_READONLY_SCOPES

    client_secret_path = pathlib.Path(client_secret_path)
    token_path = pathlib.Path(token_path)
    credentials = None

    try:
        if token_path.exists():
            credentials = Credentials.from_authorized_user_file(
                str(token_path), scopes
            )
            logger.info("Loaded cached credentials from %s", token_path)

        if credentials and credentials.expired and credentials.refresh_token:
            logger.info("Refreshing expired credentials")
            credentials.refresh(Request())
            _save_token(credentials, token_path)

        if not credentials or not credentials.valid:
            logger.info("No valid credentials found — launching OAuth flow")
            if not client_secret_path.exists():
                raise FileNotFoundError(
                    f"Client secret file not found: {client_secret_path}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret_path), scopes
            )
            credentials = flow.run_local_server(port=0)
            _save_token(credentials, token_path)
            logger.info("OAuth flow completed successfully")

    except FileNotFoundError:
        raise
    except Exception as exc:
        logger.error("Authentication failed: %s", exc)
        raise RuntimeError(f"Google OAuth authentication failed: {exc}") from exc

    return credentials


def build_drive_service(credentials: Credentials):
    """Build an authorised Google Drive v3 service resource."""
    try:
        service = build("drive", "v3", credentials=credentials)
        logger.info("Drive service built successfully")
        return service
    except Exception as exc:
        logger.error("Failed to build Drive service: %s", exc)
        raise RuntimeError(f"Failed to build Drive service: {exc}") from exc


def _save_token(credentials: Credentials, token_path: pathlib.Path) -> None:
    """Persist credentials to disk for reuse across runs."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json())
    logger.info("Token saved to %s", token_path)
