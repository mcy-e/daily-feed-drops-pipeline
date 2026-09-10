# Pipeline Architecture

This document describes the flow of the Daily Feed Drops automation pipeline.

## 1. Trigger
The pipeline is triggered primarily by **GitHub Actions** via a cron schedule defined in `.github/workflows/run-content.yml`. It runs exactly 5 times a day.

## 2. Manager Configuration Sync
The pipeline reads its schedule and target settings from `config/manager_config.json`. This config allows a local desktop manager application to push settings to the cloud repository, enabling remote control over the pipeline times without editing code directly.

## 3. Data Fetching (`scripts/generators/`)
- **Memes:** The pipeline queries the `meme-api.com` or `pullpush.io` APIs to find the latest trending memes.
- **B-roll:** Background videos (e.g., Minecraft parkour, GTA racing) are fetched from Google Drive or local caching.
- **Fallbacks:** If network sources fail (due to IP bans), a local `cursed_bank.json` and `meme_bank.json` ensure the pipeline continues operating.

## 4. Script Generation
Using the Groq API (Llama 3) or Gemini API, the pipeline generates a funny, short-form voiceover script based on the fetched images.

## 5. Audio Processing (`scripts/voice/`)
The script text is sent to `edge-tts` to generate high-quality neural voiceover audio files.

## 6. Rendering (`scripts/render/`)
The system uses **FFmpeg** to:
- Combine the background B-roll and the voiceover audio.
- Overlay the fetched meme images sequentially.
- Dynamically add styling, scaling, and transitions.

## 7. Delivery (`scripts/upload/` & `scripts/notifications/`)
- **YouTube:** Uses the Google API Client (`google-api-python-client`) to upload the rendered MP4 file to YouTube Shorts.
- **Telegram:** Sends a success notification with the YouTube URL to the designated Telegram Chat. If YouTube upload fails, the raw `.mp4` file is sent via Telegram so the video is never lost.
