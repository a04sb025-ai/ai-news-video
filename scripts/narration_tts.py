#!/usr/bin/env python3
"""Synthesize the one published narration track for adaptive AI-news videos.

Production prefers OpenAI speech when an API key is present. Offline CI keeps
Open JTalk as a deterministic fallback so tests never require network access.
A configured production provider fails closed: if OpenAI speech fails, callers
retry the render instead of silently publishing the Open JTalk prosody that has
shown recurring local slow-motion artifacts.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
import wave
from pathlib import Path

OPENAI_SPEECH_URL = "https://api.openai.com/v1/audio/speech"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini-tts-2025-12-15"
DEFAULT_OPENAI_VOICE = "marin"
DEFAULT_OPENAI_SPEED = 1.0
DEFAULT_OPENAI_INSTRUCTIONS = (
    "自然な日本語の短いニュース解説として、明瞭で一定のテンポで話してください。"
    "語尾や文中の一部だけを不自然に引き延ばしたり、急に速度や音程を落としたりしないでください。"
    "落ち着きは保ちつつ、スマートフォンの短尺動画で聞き取りやすい自然な抑揚にしてください。"
)


def _wav_pcm_data_bytes(path: Path) -> int | None:
    """Return the physically present PCM data bytes, even for streaming WAV headers.

    Some speech APIs emit RIFF/WAV with a sentinel data chunk size of 0xFFFFFFFF
    because the response is streamed before the final payload length is known.
    Python's wave module interprets that sentinel as 2,147,483,647 mono 16-bit
    frames, which at 24 kHz looks like ~24.9 hours of audio. The actual PCM bytes
    are still present in the file, so derive duration from the payload on disk.
    """
    file_size = path.stat().st_size
    if file_size < 20:
        return None

    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12 or header[:4] not in {b"RIFF", b"RF64"} or header[8:12] != b"WAVE":
            return None

        offset = 12
        while offset + 8 <= file_size:
            handle.seek(offset)
            chunk_header = handle.read(8)
            if len(chunk_header) != 8:
                return None
            chunk_id = chunk_header[:4]
            chunk_size = int.from_bytes(chunk_header[4:8], "little")
            data_start = offset + 8
            available = max(0, file_size - data_start)

            if chunk_id == b"data":
                if chunk_size == 0xFFFFFFFF or chunk_size > available:
                    return available
                return chunk_size

            if chunk_size > available:
                return None
            offset = data_start + chunk_size + (chunk_size & 1)

    return None


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as audio:
        sample_rate = audio.getframerate()
        channels = audio.getnchannels()
        sample_width = audio.getsampwidth()
        declared_frames = audio.getnframes()

    bytes_per_frame = channels * sample_width
    data_bytes = _wav_pcm_data_bytes(path)
    if data_bytes is not None and bytes_per_frame > 0:
        frames = data_bytes / bytes_per_frame
    else:
        frames = declared_frames

    duration = frames / sample_rate if sample_rate > 0 else 0.0
    if duration <= 0:
        raise RuntimeError(f"TTS produced an empty WAV: {path}")
    return duration


def synthesize_open_jtalk(
    text: str,
    output: Path,
    *,
    dictionary: Path,
    voice: Path,
    rate: float,
) -> dict:
    source = output.with_suffix(".txt")
    source.write_text(text.strip() + "\n")
    subprocess.run([
        "open_jtalk", "-x", str(dictionary), "-m", str(voice), "-r", str(rate),
        "-ow", str(output), str(source),
    ], check=True)
    duration = wav_duration(output)
    return {
        "provider": "open_jtalk",
        "model": "hts-voice",
        "voice": voice.name,
        "speed": rate,
        "duration_seconds": duration,
        "production_preferred": False,
    }


def synthesize_openai(text: str, output: Path, *, api_key: str) -> dict:
    model = os.environ.get("AI_NEWS_TTS_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    voice = os.environ.get("AI_NEWS_TTS_VOICE", DEFAULT_OPENAI_VOICE).strip() or DEFAULT_OPENAI_VOICE
    instructions = os.environ.get("AI_NEWS_TTS_INSTRUCTIONS", DEFAULT_OPENAI_INSTRUCTIONS).strip()
    speed = float(os.environ.get("AI_NEWS_TTS_SPEED", str(DEFAULT_OPENAI_SPEED)))
    if not 0.25 <= speed <= 4.0:
        raise RuntimeError("AI_NEWS_TTS_SPEED must be between 0.25 and 4.0")
    if not text.strip():
        raise RuntimeError("Narration text must not be empty")
    if len(text) > 4096:
        raise RuntimeError("Narration exceeds the speech endpoint 4096-character limit")

    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "instructions": instructions,
        "response_format": "wav",
        "speed": speed,
    }
    request = urllib.request.Request(
        OPENAI_SPEECH_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            audio = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"OpenAI speech request failed ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"OpenAI speech request failed: {error.reason}") from error

    output.write_bytes(audio)
    duration = wav_duration(output)
    return {
        "provider": "openai",
        "model": model,
        "voice": voice,
        "speed": speed,
        "duration_seconds": duration,
        "production_preferred": True,
    }


def synthesize_published_narration(
    text: str,
    output: Path,
    *,
    dictionary: Path,
    voice: Path,
    open_jtalk_rate: float,
) -> dict:
    """Create the exact WAV used by the published video.

    Provider selection is explicit when AI_NEWS_TTS_PROVIDER is set. Otherwise,
    OpenAI is selected whenever OPENAI_API_KEY exists; offline environments fall
    back to Open JTalk. An OpenAI failure never silently falls back in production.
    """
    configured = os.environ.get("AI_NEWS_TTS_PROVIDER", "").strip().lower()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    provider = configured or ("openai" if api_key else "open_jtalk")

    if provider == "openai":
        if not api_key:
            raise RuntimeError("AI_NEWS_TTS_PROVIDER=openai requires OPENAI_API_KEY")
        return synthesize_openai(text, output, api_key=api_key)
    if provider == "open_jtalk":
        return synthesize_open_jtalk(
            text,
            output,
            dictionary=dictionary,
            voice=voice,
            rate=open_jtalk_rate,
        )
    raise RuntimeError(f"Unsupported AI_NEWS_TTS_PROVIDER: {provider}")
