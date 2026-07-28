import logging
import pathlib
import random
import requests
import time
import urllib3
import os
import base64
import subprocess
import urllib.parse
import uuid

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from scripts.constants import (
    DEFAULT_DOWNLOAD_DIR,
    POLLINATIONS_API_URL,
    FOOTBALL_PROMPT_CATEGORIES,
    MIN_IMAGES_PER_VIDEO,
    MAX_IMAGES_PER_VIDEO,
    IMAGE_DURATION_MIN,
    IMAGE_DURATION_MAX,
    CROSSFADE_DURATION_MIN,
    CROSSFADE_DURATION_MAX,
    KEN_BURNS_EFFECTS,
    GEMINI_API_KEY_ENV_VAR,
)
from scripts.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

def generate_football_content(dest_dir: str | pathlib.Path = DEFAULT_DOWNLOAD_DIR) -> str:
    """Generate football AI content using Gemini/Pollinations and build a zoompan video."""
    dest_dir = pathlib.Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    num_images = random.randint(MIN_IMAGES_PER_VIDEO, MAX_IMAGES_PER_VIDEO)
    
    # Cycle through shot-type categories so every run gets a varied sequence
    prompts = [
        random.choice(FOOTBALL_PROMPT_CATEGORIES[i % len(FOOTBALL_PROMPT_CATEGORIES)])
        for i in range(num_images)
    ]
    
    logger.info("Generating %d football images...", num_images)
    image_paths = []
    run_id = uuid.uuid4().hex[:8]
    
    @retry_with_backoff(max_retries=3, delays=(5, 10, 20))
    def _download_image(img_url: str, img_path: pathlib.Path):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(img_url, headers=headers, timeout=60, verify=False)
        resp.raise_for_status()
        with open(img_path, "wb") as f:
            f.write(resp.content)

    def _generate_with_gemini(prompt_text: str, img_path: pathlib.Path):
        api_key = os.getenv(GEMINI_API_KEY_ENV_VAR)
        if not api_key:
            raise ValueError("Gemini API key not found in environment variables.")
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text}
                    ]
                }
            ]
        }
        
        resp = requests.post(url, json=payload, timeout=60, verify=False)
        resp.raise_for_status()
        resp_data = resp.json()
        
        try:
            parts = resp_data["candidates"][0]["content"]["parts"]
            for part in parts:
                if "inlineData" in part:
                    img_data = part["inlineData"]["data"]
                    with open(img_path, "wb") as f:
                        f.write(base64.b64decode(img_data))
                    return
            raise ValueError("No inlineData found in Gemini response.")
        except Exception as e:
            raise ValueError(f"Failed to parse Gemini response: {e}. Raw response keys: {list(resp_data.keys())}")

    for i, prompt in enumerate(prompts):
        encoded_prompt = urllib.parse.quote(prompt)
        # Unique seed per slot ensures the server never serves a cached image across slots
        slot_seed = random.randint(1, 999999)
        pollinations_url = (
            POLLINATIONS_API_URL.format(prompt=encoded_prompt)
            + f"&seed={slot_seed}"
        )
        img_path = dest_dir / f"football_{run_id}_{i}.jpg"
        
        success = False
        
        # 1. Try Gemini
        try:
            logger.info("Attempting Gemini generation for image %d/%d", i+1, num_images)
            _generate_with_gemini(prompt, img_path)
            image_paths.append(img_path)
            success = True
            logger.info(
                "Saved image %d/%d (Gemini) → %s (%d bytes)",
                i+1, num_images, img_path, img_path.stat().st_size,
            )
            time.sleep(3)
        except Exception as e:
            logger.warning("Gemini generation failed for prompt '%s': %s. Falling back to Pollinations...", prompt, e)
            
        # 2. Try Pollinations Fallback
        if not success:
            try:
                _download_image(pollinations_url, img_path)
                image_paths.append(img_path)
                logger.info(
                    "Saved image %d/%d (Pollinations, seed=%d) → %s (%d bytes)",
                    i+1, num_images, slot_seed, img_path, img_path.stat().st_size,
                )
                time.sleep(3)
            except Exception as e:
                logger.error("Both generation methods failed for prompt '%s': %s", prompt, e)
            
    if not image_paths:
        raise RuntimeError("Failed to generate any images for football content.")

    logger.info(
        "Final image list for video assembly (%d images): %s",
        len(image_paths),
        [str(p) for p in image_paths],
    )
    return _build_zoompan_video(image_paths, dest_dir, run_id)

def _build_zoompan_video(image_paths: list[pathlib.Path], dest_dir: pathlib.Path, run_id: str) -> str:
    """Build a dynamic video from images with alternating Ken Burns effects and short crossfades."""
    logger.info("Building zoompan video from %d images...", len(image_paths))
    output_path = dest_dir / f"football_video_{run_id}.mp4"
    
    fps = 25
    n = len(image_paths)
    
    img_durations = [random.uniform(IMAGE_DURATION_MIN, IMAGE_DURATION_MAX) for _ in range(n)]
    crossfade_durations = [random.uniform(CROSSFADE_DURATION_MIN, CROSSFADE_DURATION_MAX) for _ in range(n - 1)]
    
    logger.info(
        "Image durations: %s | Crossfades: %s",
        [round(d, 2) for d in img_durations],
        [round(c, 2) for c in crossfade_durations],
    )
    
    inputs = []
    for i, p in enumerate(image_paths):
        resolved = pathlib.Path(p).resolve()
        logger.info("FFmpeg input %d → %s (%d bytes)", i, resolved, resolved.stat().st_size)
        inputs.extend(["-loop", "1", "-t", f"{img_durations[i]:.3f}", "-i", str(resolved)])
        
    filter_parts = []
    for i in range(n):
        frames = max(1, int(img_durations[i] * fps))
        effect = KEN_BURNS_EFFECTS[i % len(KEN_BURNS_EFFECTS)].format(frames=frames)
        filter_parts.append(
            f"[{i}:v]scale=1080:1920,setsar=1,format=yuv420p,"
            f"zoompan={effect}:d={frames}:s=1080x1920:fps={fps}[v{i}]"
        )
        
    if n > 1:
        current_out = "v0"
        cumulative_offset = 0.0
        for i in range(1, n):
            cumulative_offset += img_durations[i - 1] - crossfade_durations[i - 1]
            xfade_dur = crossfade_durations[i - 1]
            next_out = f"xfade{i}" if i < n - 1 else "outv"
            filter_parts.append(
                f"[{current_out}][v{i}]xfade=transition=fade"
                f":duration={xfade_dur:.3f}:offset={cumulative_offset:.3f}[{next_out}]"
            )
            current_out = next_out
    else:
        current_out = "outv"
        filter_parts.append(f"[v0]copy[{current_out}]")
        
    filter_complex = ";".join(filter_parts)
    
    cmd = [
        "ffmpeg", "-y",
    ] + inputs + [
        "-filter_complex", filter_complex,
        "-map", f"[{current_out}]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logger.info("Successfully built video at %s", output_path)
        return str(output_path)
    except subprocess.CalledProcessError as e:
        logger.error("FFmpeg failed: %s", e.stderr)
        raise RuntimeError(f"Failed to build video with ffmpeg: {e.stderr}") from e
