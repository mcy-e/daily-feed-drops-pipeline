import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

DEFAULT_CLIENT_SECRET_PATH = PROJECT_ROOT / "config" / "client_secret_fc.json"
DEFAULT_TOKEN_PATH = PROJECT_ROOT / "config" / "token_fc.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_DOWNLOAD_DIR = PROJECT_ROOT / "downloads"
DRIVE_FOLDERS_CONFIG_PATH = PROJECT_ROOT / "config" / "drive_folders.json"

DEFAULT_API_PORT = 8001

DRIVE_READONLY_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload"
]

RENDER_WIDTH = 1080
RENDER_HEIGHT = 1920

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

VIDEO_MIME_QUERY = (
    "("
    "mimeType='video/mp4' or "
    "mimeType='video/quicktime' or "
    "mimeType='video/x-msvideo' or "
    "mimeType='video/x-matroska' or "
    "mimeType='video/webm'"
    ")"
)

BLUR_SIGMA = 50
FFMPEG_CRF = 23
FFMPEG_PRESET = "fast"
WINDOW_DURATION_SECONDS = 20
WINDOW_LEAD_SECONDS = 5

EXCITEMENT_KEYWORDS = {
    "goal", "shoot", "score", "wow", "unbelievable", "amazing", 
    "brilliant", "what a", "incredible", "beautiful", "strike"
}

TELEGRAM_BOT_TOKEN_ENV_VAR = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV_VAR = "TELEGRAM_CHAT_ID"
YOUTUBE_PRIVACY_STATUS_ENV_VAR = "YOUTUBE_PRIVACY_STATUS"

USED_CLIPS_DB_PATH = PROJECT_ROOT / "data" / "used_clips.db"
