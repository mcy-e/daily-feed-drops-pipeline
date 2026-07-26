import json
import logging
import os
import pathlib
import random
import subprocess
import tempfile
import uuid

import numpy as np
import whisper

from scripts.constants import (
    EXCITEMENT_KEYWORDS,
    WINDOW_DURATION_SECONDS,
    WINDOW_LEAD_SECONDS,
)
from scripts.render.render import probe_video

logger = logging.getLogger(__name__)


def find_highlight_candidates(input_path: str | pathlib.Path, num_candidates: int = 3) -> list[float]:
    """Extract audio, find energy peaks, return the top N start times for windows."""
    input_path = pathlib.Path(input_path)
    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as temp_audio:
        temp_audio_path = temp_audio.name

    try:
        cmd = [
            "ffmpeg", "-i", str(input_path), "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1", "-y", temp_audio_path,
        ]
        logger.info("Extracting audio for analysis: %s", input_path.name)
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        audio_data = np.fromfile(temp_audio_path, dtype=np.int16)
        if len(audio_data) == 0:
            return [0.0]

        sample_rate = 16000
        window_samples = WINDOW_DURATION_SECONDS * sample_rate

        if len(audio_data) <= window_samples:
            return [0.0]

        audio_float = audio_data.astype(np.float32)
        energy = audio_float ** 2
        
        # Smooth the energy to find peaks (using a 1s window)
        smooth_window = np.ones(sample_rate)
        smoothed_energy = np.correlate(energy, smooth_window, mode='valid')

        candidates = []
        # Find top N local peaks separated by at least window_duration
        temp_energy = smoothed_energy.copy()
        for _ in range(num_candidates):
            max_idx = np.argmax(temp_energy)
            if temp_energy[max_idx] == 0:
                break
                
            peak_time = max_idx / sample_rate
            start_time = max(0.0, peak_time - WINDOW_LEAD_SECONDS)
            
            candidates.append(start_time)
            
            # Zero out the neighbourhood of the peak to find distinct events
            zero_start = max(0, int((peak_time - WINDOW_DURATION_SECONDS) * sample_rate))
            zero_end = min(len(temp_energy), int((peak_time + WINDOW_DURATION_SECONDS) * sample_rate))
            temp_energy[zero_start:zero_end] = 0

        return sorted(candidates) if candidates else [0.0]

    except subprocess.CalledProcessError as exc:
        logger.error("Failed to extract audio: %s", exc.stderr)
        return [0.0]
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)


def score_transcript(result: dict) -> int:
    """Score a Whisper result dictionary based on excitement keywords."""
    score = 0
    text = result.get("text", "").lower()
    for kw in EXCITEMENT_KEYWORDS:
        if kw in text:
            score += 1
    return score


def extract_audio_segment(input_path: pathlib.Path, start_time: float, duration: float) -> str:
    """Extract a specific slice of audio to a temporary wav file."""
    temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    cmd = [
        "ffmpeg", "-ss", str(start_time), "-t", str(duration),
        "-i", str(input_path), "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1", "-y", temp_wav,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return temp_wav


def write_srt(result: dict, start_offset: float, output_path: str):
    """Write Whisper segments to an SRT file, adjusting timestamps by start_offset."""
    def format_time(seconds):
        ms = int((seconds % 1) * 1000)
        s = int(seconds)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(output_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(result.get("segments", []), start=1):
            start = format_time(segment["start"])
            end = format_time(segment["end"])
            text = segment["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


def smart_trim_analysis(input_path: str | pathlib.Path, output_dir: str | pathlib.Path) -> tuple[float, float, str]:
    """
    Find best 20s window, run Whisper, generate SRT.
    Returns (start_time, end_time, srt_path)
    """
    input_path = pathlib.Path(input_path)
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    probe = probe_video(input_path)
    duration = probe["duration"]

    if duration <= WINDOW_DURATION_SECONDS:
        start_time = 0.0
        end_time = duration
    else:
        logger.info("Finding peak audio candidates for %s", input_path.name)
        candidates = find_highlight_candidates(input_path)
        logger.info("Found candidates at: %s", [f"{c:.2f}s" for c in candidates])

        best_score = -1
        best_candidate = candidates[0]
        best_result = None

        logger.info("Loading Whisper model (base)")
        model = whisper.load_model("base")

        for start_time in candidates:
            # Extract the 20s audio clip
            temp_wav = extract_audio_segment(input_path, start_time, WINDOW_DURATION_SECONDS)
            try:
                # Transcribe
                logger.info("Transcribing candidate at %.2fs", start_time)
                result = model.transcribe(temp_wav, fp16=False)
                score = score_transcript(result)
                logger.info("Score for %.2fs: %d (Text: '%s')", start_time, score, result.get("text", "")[:50])

                if score > best_score:
                    best_score = score
                    best_candidate = start_time
                    best_result = result
            finally:
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)

        start_time = best_candidate
        end_time = min(duration, start_time + WINDOW_DURATION_SECONDS)
        logger.info("Selected best window: %.2fs -> %.2fs (Score: %d)", start_time, end_time, best_score)
    
    # Generate SRT for the winning window
    srt_path = output_dir / f"{input_path.stem}.srt"
    
    if duration <= WINDOW_DURATION_SECONDS:
        logger.info("Transcribing full video (duration <= %ds)", WINDOW_DURATION_SECONDS)
        model = whisper.load_model("base")
        temp_wav = extract_audio_segment(input_path, 0.0, duration)
        best_result = model.transcribe(temp_wav, fp16=False)
        os.remove(temp_wav)
        
    write_srt(best_result, start_offset=0, output_path=str(srt_path))
    logger.info("Generated subtitles at %s", srt_path.name)

    return start_time, end_time, str(srt_path)


def simple_trim_analysis(input_path: str | pathlib.Path) -> tuple[float, float, None]:
    """
    Simple fallback that takes a random 15-20s segment without generating captions or detecting peaks.
    Used for stock/own footage.
    """
    input_path = pathlib.Path(input_path)
    probe = probe_video(input_path)
    duration = probe["duration"]
    
    if duration <= WINDOW_DURATION_SECONDS:
        start_time = 0.0
        end_time = duration
    else:
        # Pick a random start time that allows for a full window
        max_start = duration - WINDOW_DURATION_SECONDS
        start_time = random.uniform(0.0, max_start)
        end_time = start_time + WINDOW_DURATION_SECONDS
        
    logger.info("Simple trim selected window: %.2fs -> %.2fs", start_time, end_time)
    return start_time, end_time, None


def curated_trim_analysis(
    input_path: str | pathlib.Path,
    output_dir: str | pathlib.Path,
    start_time: float,
    end_time: float,
) -> tuple[float, float, str]:
    """
    Generate captions for a fixed curated window by transcribing just that segment.
    Skips peak detection entirely — timestamps are provided by the companion JSON.
    """
    input_path = pathlib.Path(input_path)
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = end_time - start_time
    logger.info("Curated trim: transcribing fixed window %.2fs -> %.2fs", start_time, end_time)

    temp_wav = extract_audio_segment(input_path, start_time, duration)
    try:
        model = whisper.load_model("base")
        result = model.transcribe(temp_wav, fp16=False)
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)

    srt_path = output_dir / f"{input_path.stem}.srt"
    write_srt(result, start_offset=0, output_path=str(srt_path))
    logger.info("Generated curated subtitles at %s", srt_path.name)

    return start_time, end_time, str(srt_path)
