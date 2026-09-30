#!/usr/bin/env python3
"""Audio-led scene-boundary alignment helpers for synthetic narration WAV files."""
from __future__ import annotations

from array import array
import math
import re
import sys
import wave
from pathlib import Path

SILENCE_THRESHOLD_DBFS = -35.0
SILENCE_WINDOW_SECONDS = 0.01
SILENCE_MIN_SECONDS = 0.08
BOUNDARY_SEARCH_SECONDS = 2.50
SCENE_SWITCH_DELAY_SECONDS = 0.12
MIN_BOUNDARY_GAP_SECONDS = 0.20
TERMINAL_PUNCTUATION = ("。", "！", "？", "!", "?")


def ensure_terminal_pause(text: str) -> str:
    """Ensure each authored cue ends with punctuation that yields a natural phrase pause."""
    value = text.strip()
    if not value:
        return value
    if value.endswith(TERMINAL_PUNCTUATION):
        return value
    return value + "。"


def detect_silence_regions(
    wav_path: Path,
    *,
    threshold_dbfs: float = SILENCE_THRESHOLD_DBFS,
    window_seconds: float = SILENCE_WINDOW_SECONDS,
    min_silence_seconds: float = SILENCE_MIN_SECONDS,
) -> list[dict[str, float]]:
    """Return low-energy regions measured directly from a 16-bit PCM WAV.

    Open JTalk emits deterministic PCM WAV files, so doing this in-process avoids
    depending on ffmpeg log parsing and lets the final published WAV remain the
    single source of truth for visual timing.
    """
    with wave.open(str(wav_path), "rb") as audio:
        channels = audio.getnchannels()
        sample_width = audio.getsampwidth()
        sample_rate = audio.getframerate()
        frame_count = audio.getnframes()
        payload = audio.readframes(frame_count)

    if sample_width != 2:
        raise ValueError(f"silence detection requires 16-bit PCM WAV; got sample width {sample_width}")
    if channels < 1 or sample_rate <= 0:
        raise ValueError("invalid WAV metadata for silence detection")

    samples = array("h")
    samples.frombytes(payload)
    if sys.byteorder != "little":
        samples.byteswap()

    threshold = 32767 * math.pow(10.0, threshold_dbfs / 20.0)
    window_frames = max(1, round(sample_rate * window_seconds))
    silent_windows: list[tuple[float, float]] = []

    for frame_start in range(0, frame_count, window_frames):
        frame_end = min(frame_count, frame_start + window_frames)
        sample_start = frame_start * channels
        sample_end = frame_end * channels
        peak = max((abs(sample) for sample in samples[sample_start:sample_end]), default=0)
        if peak <= threshold:
            silent_windows.append((frame_start / sample_rate, frame_end / sample_rate))

    regions: list[dict[str, float]] = []
    if not silent_windows:
        return regions

    region_start, region_end = silent_windows[0]
    tolerance = max(window_seconds * 1.5, 0.002)
    for start, end in silent_windows[1:]:
        if start <= region_end + tolerance:
            region_end = end
            continue
        if region_end - region_start >= min_silence_seconds:
            regions.append({"start": region_start, "end": region_end, "duration": region_end - region_start})
        region_start, region_end = start, end
    if region_end - region_start >= min_silence_seconds:
        regions.append({"start": region_start, "end": region_end, "duration": region_end - region_start})
    return regions



def split_subtitle_text(text: str, *, max_chunks: int = 3, soft_chars: int = 24) -> list[str]:
    """Split viewer subtitle text at authored Japanese phrase boundaries.

    Sentence punctuation is preferred. A long single sentence may split at commas,
    but words are never rewritten or dropped.
    """
    value = " ".join(str(text).replace("\n", " ").split()).strip()
    if not value:
        return []

    chunks = [part.strip() for part in re.findall(r"[^。！？!?]+[。！？!?]?", value) if part.strip()]
    if len(chunks) == 1 and len(value) > soft_chars:
        comma_chunks = [part.strip() for part in re.findall(r"[^、，,]+[、，,]?", value) if part.strip()]
        if len(comma_chunks) > 1:
            chunks = comma_chunks

    while len(chunks) > max_chunks:
        # Merge the lightest adjacent pair so order and wording remain unchanged.
        pair_index = min(
            range(len(chunks) - 1),
            key=lambda index: len(chunks[index]) + len(chunks[index + 1]),
        )
        chunks[pair_index:pair_index + 2] = [chunks[pair_index] + chunks[pair_index + 1]]
    return chunks


def align_subtitle_segments(
    text: str,
    start: float,
    speech_end: float,
    silence_regions: list[dict[str, float]],
    *,
    max_chunks: int = 3,
    search_seconds: float = 1.25,
    min_gap_seconds: float = 0.25,
) -> list[dict[str, float | str]]:
    """Align subtitle phrase changes to pauses measured in the final published WAV.

    Text is never used to drive the audio. Character weights only estimate each
    phrase boundary; a nearby low-energy pause in the final WAV is preferred.
    """
    chunks = split_subtitle_text(text, max_chunks=max_chunks)
    start = float(start)
    speech_end = float(speech_end)
    if not chunks or speech_end <= start:
        return []
    if len(chunks) == 1:
        return [{"start": round(start, 4), "end": round(speech_end, 4), "text": chunks[0]}]

    weights = [max(1, sum(1 for char in chunk if not char.isspace())) for chunk in chunks]
    total_weight = sum(weights)
    targets = []
    cumulative = 0
    for weight in weights[:-1]:
        cumulative += weight
        targets.append(start + (speech_end - start) * cumulative / total_weight)

    candidates = []
    for index, region in enumerate(silence_regions):
        region_start = float(region["start"])
        region_end = float(region["end"])
        if region_end <= start or region_start >= speech_end:
            continue
        switch = max(region_start, min(region_start + 0.08, region_end - 0.02))
        if start + min_gap_seconds <= switch <= speech_end - min_gap_seconds:
            candidates.append((index, switch))

    # A subtitle must never advance while the narrator is still speaking.
    # If no real pause exists near an estimated text boundary, keep the current
    # subtitle visible and merge the next chunk into it instead of inventing a
    # proportional timestamp inside active speech.
    selected = []
    used = set()
    previous = start
    for boundary_index, target in enumerate(targets):
        remaining = len(targets) - boundary_index - 1
        minimum = previous + min_gap_seconds
        maximum = speech_end - min_gap_seconds * (remaining + 1)
        eligible = [
            item for item in candidates
            if item[0] not in used
            and minimum <= item[1] <= maximum
            and abs(item[1] - target) <= search_seconds
        ]
        if not eligible:
            continue
        region_index, chosen = min(eligible, key=lambda item: abs(item[1] - target))
        used.add(region_index)
        chosen = round(chosen, 4)
        selected.append((boundary_index, chosen))
        previous = chosen

    segments = []
    segment_start = round(start, 4)
    chunk_start = 0
    for boundary_index, boundary in selected:
        text_value = "".join(chunks[chunk_start:boundary_index + 1])
        if boundary > segment_start and text_value:
            segments.append({"start": segment_start, "end": boundary, "text": text_value})
        segment_start = boundary
        chunk_start = boundary_index + 1

    tail_text = "".join(chunks[chunk_start:])
    if speech_end > segment_start and tail_text:
        segments.append({"start": segment_start, "end": round(speech_end, 4), "text": tail_text})
    return segments

def proportional_boundary_targets(probe_durations: list[float], narration_duration: float) -> list[float]:
    """Estimate cue boundaries before snapping them to measured final-WAV pauses."""
    if not probe_durations or narration_duration <= 0:
        return []
    total = sum(probe_durations)
    if total <= 0:
        return []
    scale = narration_duration / total
    targets = []
    cursor = 0.0
    for duration in probe_durations[:-1]:
        cursor += duration * scale
        targets.append(cursor)
    return targets


def _switch_point(region: dict[str, float], delay_seconds: float) -> float:
    """Switch shortly after speech ends while keeping a little silence before the next cue."""
    start = float(region["start"])
    end = float(region["end"])
    if end <= start:
        return start
    tail_guard = min(0.03, max(0.0, (end - start) * 0.25))
    return max(start, min(start + delay_seconds, end - tail_guard))


def snap_scene_boundaries(
    probe_durations: list[float],
    narration_duration: float,
    silence_regions: list[dict[str, float]],
    *,
    search_seconds: float = BOUNDARY_SEARCH_SECONDS,
    switch_delay_seconds: float = SCENE_SWITCH_DELAY_SECONDS,
    min_gap_seconds: float = MIN_BOUNDARY_GAP_SECONDS,
) -> tuple[list[float], list[dict[str, float | str | None]]]:
    """Snap proportional cue estimates to nearby real pauses in the final narration.

    Each selected boundary is constrained to remain ordered. The renderer uses a
    wider search window because a continuous natural TTS pass can speak a cue more
    slowly or quickly than the local probe. Publication code rejects any remaining
    proportional fallback, so visuals never intentionally switch mid-speech.
    """
    targets = proportional_boundary_targets(probe_durations, narration_duration)
    if not targets:
        return [], []

    candidates = []
    for index, region in enumerate(silence_regions):
        switch = _switch_point(region, switch_delay_seconds)
        if 0.0 < switch < narration_duration:
            candidates.append((index, region, switch))

    boundaries: list[float] = []
    details: list[dict[str, float | str | None]] = []
    used_regions: set[int] = set()
    previous = 0.0
    total_boundaries = len(targets)

    for boundary_index, target in enumerate(targets):
        remaining = total_boundaries - boundary_index - 1
        minimum = previous + min_gap_seconds
        maximum = narration_duration - min_gap_seconds * (remaining + 1)
        if maximum < minimum:
            maximum = minimum

        eligible = [
            item for item in candidates
            if item[0] not in used_regions
            and minimum <= item[2] <= maximum
            and abs(item[2] - target) <= search_seconds
        ]
        if eligible:
            region_index, region, chosen = min(
                eligible,
                key=lambda item: (abs(item[2] - target), -float(item[1]["duration"])),
            )
            used_regions.add(region_index)
            method = "silence-snapped"
            silence_start = float(region["start"])
            silence_end = float(region["end"])
        else:
            chosen = min(max(target, minimum), maximum)
            method = "proportional-fallback"
            silence_start = None
            silence_end = None

        chosen = round(chosen, 4)
        boundaries.append(chosen)
        details.append({
            "target": round(target, 4),
            "boundary": chosen,
            "method": method,
            "silence_start": round(silence_start, 4) if silence_start is not None else None,
            "silence_end": round(silence_end, 4) if silence_end is not None else None,
        })
        previous = chosen

    return boundaries, details
