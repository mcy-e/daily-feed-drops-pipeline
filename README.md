# Daily Feed Drops Pipeline

Automated short-form content generation pipeline that creates, edits, and uploads videos to YouTube Shorts entirely hands-free.

> **Note on Creation:** 
> This entire system was brainstormed, architected, and directed by **mcy-e** (handcrafted logic and workflow design), while the code itself was 100% "vibe coded" (written) by AI. 

## Features
- **Meme Recap Shorts:** Automatically fetches trending memes from Reddit and APIs, uses Gemini/Groq to generate a funny, fast-paced voiceover script, and renders a 40-second vertical video with background gameplay (B-roll) and AI TTS.
- **Fully Automated:** Runs on a strict 5-times-a-day schedule using GitHub Actions.
- **Resilient Fallbacks:** If the primary network APIs (like Reddit or PullPush) block the datacenter IP, the system seamlessly falls back to a local hand-curated JSON bank of content so the pipeline *never* misses an upload.
- **Platform Sync:** Built-in Telegram notifications for success/failure alerts with direct video fallback delivery.

## Architecture & Workflow
The system consists of several specialized modules:
1. **Generators (`scripts/generators/`)**: Fetches memes, background video clips (B-roll), and generates scripts via LLMs.
2. **Voice (`scripts/voice/`)**: Converts the generated script into high-quality TTS audio (via Edge TTS).
3. **Render (`scripts/render/`)**: Uses FFmpeg to dynamically composite the B-roll, memes, audio, and visual assets into a final vertical video.
4. **Upload (`scripts/upload/`)**: Handles the Google OAuth 2.0 flow and YouTube Data API upload process.
5. **Notifications (`scripts/notifications/`)**: Pings Telegram with the video link or the raw MP4 if upload fails.

See the `docs/` folder for more detailed architecture diagrams.

## Setup Requirements

If you are running this locally or forking it, you will need:
- FFmpeg installed (`apt-get install ffmpeg` or Windows equivalent)
- Python 3.11+
- Various API Keys stored in an `.env` file or GitHub Secrets:
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
  - `GEMINI_API_KEY`, `GROQ_API_KEY`
  - `PEXELS_API_KEY`
  - `GOOGLE_OAUTH_TOKEN_B64`, `GOOGLE_CLIENT_SECRET_B64` (Base64 encoded for CI/CD)

## License
MIT License. Feel free to fork and learn from the automation logic!
