"""
Run this script locally to refresh your Google OAuth token.
It will open a browser window, ask you to log in, and save the new token.

Usage:
    python refresh_token.py
"""
import logging
import pathlib
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]

CLIENT_SECRET = pathlib.Path("config/client_secret_v2.json")
TOKEN_PATH = pathlib.Path("config/token_v2.json")


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        logger.error("Missing dependency. Run: pip install google-auth-oauthlib")
        sys.exit(1)

    if not CLIENT_SECRET.exists():
        logger.error("client_secret_v2.json not found at: %s", CLIENT_SECRET)
        logger.error("Make sure you are running this from the pipeline root directory.")
        sys.exit(1)

    logger.info("Opening browser for Google login...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    credentials = flow.run_local_server(port=0)

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(credentials.to_json())
    logger.info("Token saved to %s", TOKEN_PATH)
    logger.info("Now run the following command to copy it to your clipboard:")
    logger.info(
        r'  [Convert]::ToBase64String([IO.File]::ReadAllBytes("config\token_v2.json")) | Set-Clipboard'
    )
    logger.info("Then update the GOOGLE_OAUTH_TOKEN_B64 secret on GitHub.")


if __name__ == "__main__":
    main()
