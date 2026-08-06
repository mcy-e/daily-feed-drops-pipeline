import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

DEFAULT_CLIENT_SECRET_PATH = PROJECT_ROOT / "config" / "client_secret_v2.json"
DEFAULT_TOKEN_PATH = PROJECT_ROOT / "config" / "token_v2.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_DOWNLOAD_DIR = PROJECT_ROOT / "downloads"
DRIVE_FOLDERS_CONFIG_PATH = PROJECT_ROOT / "config" / "drive_folders.json"

# Shared pipeline temp/output directory
TEMP_DIR = PROJECT_ROOT / "temp"

# Legacy alias kept for backwards compatibility
CHANNELS: list = []

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
GEMINI_API_KEY_ENV_VAR = "GEMINI_API_KEY"
GROQ_API_KEY_ENV_VAR = "GROQ_API_KEY"
OPENROUTER_API_KEY_ENV_VAR = "OPENROUTER_API_KEY"

COMMENTARY_ENABLED = True

USED_CLIPS_DB_PATH = PROJECT_ROOT / "data" / "used_clips.db"

POLLINATIONS_API_URL = "https://image.pollinations.ai/prompt/{prompt}?width=1080&height=1920&nologo=true"

# Each inner list is a shot-type category. Images are sampled by cycling through categories
# so every run alternates: wide → close-up → action → gear → wide …
FOOTBALL_PROMPT_CATEGORIES = [
    # wide establishing shots
    [
        "Wide angle cinematic shot of a floodlit football stadium at night, wet pitch gleaming, dramatic atmosphere, 8k",
        "Aerial cinematic view of a football pitch with players mid-match, stadium packed with fans, golden hour lighting",
        "Long shot of a lone football on an empty stadium pitch under rain, moody dramatic lighting, photorealistic",
    ],
    # close-up detail shots
    [
        "Extreme close up of professional goalkeeper gloves catching a fast football, dirt and sweat flying, 4k photorealistic",
        "Macro close up of a football's leather panels glistening with rain, dramatic studio rim lighting, 8k",
        "Close up of a football boot in the instant of striking the ball, mud splashing outward, cinematic slow motion look",
        "Detail shot of football boot laces and studs on wet grass, shallow depth of field, cinematic",
    ],
    # dramatic action-angle shots
    [
        "POV shot from a goalkeeper's perspective, a penalty taker running up, stadium roaring, cinematic",
        "Dynamic low angle shot of a football player kicking the ball under heavy rain, water exploding outward, 8k",
        "POV shot from inside the goal net as a football crashes into the top corner, stadium erupting, dramatic lighting",
        "First-person POV sprint down the wing with the ball, opposition defenders blurred, stadium lights streaking",
    ],
    # gear showcase shots
    [
        "A pair of futuristic neon-accented football boots on a sleek locker room bench, dramatic rim lighting, photorealistic product shot",
        "A golden match football on a black marble pedestal with dramatic spotlight, 3D render style, luxury product shot",
        "A glowing football leaving a trail of fire through a dark stadium, cinematic action, 4k",
        "Professional goalkeeper gloves on a dark surface, dramatic rim lighting, photorealistic studio product shot",
    ],
]

MIN_IMAGES_PER_VIDEO = 8
MAX_IMAGES_PER_VIDEO = 10
IMAGE_DURATION_MIN = 1.5
IMAGE_DURATION_MAX = 2.0
CROSSFADE_DURATION_MIN = 0.2
CROSSFADE_DURATION_MAX = 0.3

# Each string is a zoompan z/x/y expression format template — {frames} is substituted per image.
# Cycled per image to alternate Ken Burns direction.
KEN_BURNS_EFFECTS = [
    "z='min(1+on*0.3/{frames},1.3)':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'",
    "z='max(1.3-on*0.3/{frames},1.0)':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'",
    "z=1.2:x='(iw-iw/zoom)*on/{frames}':y='(ih-ih/zoom)/2'",
    "z=1.2:x='(iw-iw/zoom)*(1-on/{frames})':y='(ih-ih/zoom)/2'",
]

# --- Shared content pipeline ---

DEFAULT_TEMP_DIR = PROJECT_ROOT / "temp"
MANAGER_CONFIG_PATH = PROJECT_ROOT / "config" / "manager_config.json"

CONTENT_TYPES = (
    "explained_topic",
    "dark_facts",
    "football_trivia",
    "viral_news",
    "quiz_riddle",
    "meme_recap",
    "motivation_content",
    "would_you_rather",
)

PEXELS_API_KEY_ENV_VAR = "PEXELS_API_KEY"
GNEWS_API_KEY_ENV_VAR = "GNEWS_API_KEY"

GEMINI_TEXT_MODEL = "gemini-2.0-flash"
GROQ_MODEL = "llama-3.1-8b-instant"
OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
TTS_VOICE = "en-US-ChristopherNeural"

SCHEDULE_TOLERANCE_MINUTES = 29

# Topic pools / prompt seeds per content type (one chosen at random per run)
CONTENT_TOPIC_POOLS = {
    "explained_topic": [
        "Why the sky looks blue",
        "How Wi-Fi actually works",
        "What causes hiccups",
        "Why we yawn",
        "How GPS finds you anywhere",
        "Why cats purr",
        "What lightning really is",
        "How microwave ovens heat food",
    ],
    "dark_facts": [
        "The last person executed by guillotine in France",
        "How long it would take to walk to the Moon",
        "The world's deadliest animal",
        "How deep the Mariana Trench actually is",
        "The human body after 1 minute without oxygen",
        "How hot a lightning bolt really gets",
        "What happens to your body in space",
        "The oldest living thing on Earth",
        "How fast a sneeze travels",
    ],
    "would_you_rather": [
        "fly but only 3 feet off the ground vs run at 100mph",
        "know when you'll die vs know how you'll die",
        "speak every language vs play every instrument",
        "never feel pain vs never feel fear",
        "be famous for something bad vs unknown for something great",
        "only eat your favourite food forever vs never eat it again",
        "be stuck in the past vs only live in the future",
        "have wifi everywhere vs free food everywhere",
    ],
    "football_trivia": [
        "Most goals in a single World Cup",
        "Youngest player to score in the Champions League",
        "Longest unbeaten run in league football",
        "Fastest red card in history",
        "Most expensive transfer ever",
        "Highest-scoring draw in Premier League history",
        "Most capped international player",
        "Shortest manager tenure ever",
    ],
    "quiz_riddle": [
        "What has keys but no locks?",
        "I speak without a mouth and hear without ears — what am I?",
        "The more you take, the more you leave behind — what am I?",
        "What can travel around the world while staying in a corner?",
        "What gets wetter the more it dries?",
        "What has a head and a tail but no body?",
    ],
    "motivation_content": [
        "Starting over after failure",
        "The power of small daily habits",
        "When nobody believes in you",
        "Turning rejection into fuel",
        "The marathon mindset",
        "Finding strength in hard seasons",
    ],
}

VIRAL_NEWS_SUBCATEGORIES = {
    "gaming": "gaming video game release",
    "movies": "movie film premiere box office",
    "blu_ray": "blu-ray release home entertainment",
    "politics": "politics government policy",
    "tech": "technology startup AI gadget",
}

MEME_API_URL = "https://meme-api.com/gimme/5"
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"
GNEWS_SEARCH_URL = "https://gnews.io/api/v4/search"

MANIM_FRAME_WIDTH = 9
MANIM_FRAME_HEIGHT = 16
MANIM_PIXEL_WIDTH = 1080
MANIM_PIXEL_HEIGHT = 1920

# Style presets for Manim scenes (colors are hex strings)
CONTENT_STYLE_PRESETS = {
    "explained_topic": {
        "bg_color": "#0f0f0f",
        "text_color": "#ffffff",
        "accent_color": "#4fc3f7",
        "font": "Sans",
        "secondary_font": "Sans",
    },
    "dark_facts": {
        "bg_color": "#0a0a0a",
        "text_color": "#ffffff",
        "accent_color": "#ff3333",
        "font": "Sans",
        "secondary_font": "Sans",
    },
    "would_you_rather": {
        "bg_color": "#0d0d2b",
        "text_color": "#ffffff",
        "accent_color": "#6c63ff",
        "font": "Sans",
        "secondary_font": "Sans",
    },
    "football_trivia": {
        "bg_color": "#1b4332",
        "text_color": "#ffffff",
        "accent_color": "#95d5b2",
        "font": "Sans",
        "secondary_font": "Sans",
    },
    "viral_news": {
        "bg_color": "#0d1117",
        "text_color": "#ffffff",
        "accent_color": "#ff4444",
        "font": "Sans",
        "secondary_font": "Sans",
    },
    "quiz_riddle": {
        "bg_color": "#1a0a2e",
        "text_color": "#e0e0e0",
        "accent_color": "#9b59b6",
        "font": "Sans",
        "secondary_font": "Sans",
    },
    "meme_recap": {
        "bg_color": "#000000",
        "text_color": "#ffffff",
        "accent_color": "#ffffff",
        "font": "Sans",
        "secondary_font": "Sans",
    },
    "motivation_content": {
        "bg_color": "#3d2817",
        "text_color": "#fff8e7",
        "accent_color": "#ffb347",
        "font": "Georgia",
        "secondary_font": "Georgia",
    },
}

YOUTUBE_TAGS_BY_CONTENT_TYPE = {
    "explained_topic": ["explained", "facts", "education", "shorts"],
    "dark_facts": ["dark", "facts", "mindblowing", "shorts"],
    "would_you_rather": ["wouldyourather", "this", "orthat", "shorts"],
    "football_trivia": ["football", "trivia", "soccer", "shorts"],
    "viral_news": ["news", "viral", "headlines", "shorts"],
    "quiz_riddle": ["quiz", "riddle", "brainteaser", "shorts"],
    "meme_recap": ["memes", "funny", "viral", "shorts"],
    "motivation_content": ["motivation", "inspiration", "mindset", "shorts"],
}
