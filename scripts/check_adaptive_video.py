#!/usr/bin/env python3
"""Validate media basics for an adaptive explainer without forcing a fixed duration."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

video = Path(sys.argv[1])
story_path = Path(sys.argv[2])
story = json.loads(story_path.read_text())
if story.get("explanation_contract") != "adaptive-pages-v1":
    raise SystemExit("adaptive video QA requires adaptive-pages-v1 story")

ffprobe = shutil.which("ffprobe") or "ffprobe"
cmd = [
    ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
    "-of", "json", str(video),
]
try:
    info = json.loads(subprocess.check_output(cmd, text=True))
except (FileNotFoundError, subprocess.CalledProcessError) as exc:
    raise SystemExit(f"ffprobe failed: {exc}")

vstream = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
duration = float(info["format"]["duration"])
expected = float(story.get("expected_duration_seconds") or story["script"][-1]["end"])
page_count = int(story.get("adaptive_page_count") or max(0, len(story.get("script", [])) - 1))

results = {
    "duration_matches_story": abs(duration - expected) <= 0.9,
    "duration_safety_window": 15 <= duration <= 180,
    "adaptive_page_count": 4 <= page_count <= 10,
    "resolution_1080x1920": (vstream.get("width"), vstream.get("height")) == (1080, 1920),
    "audio_present": any(s.get("codec_type") == "audio" for s in info["streams"]),
}
for key, ok in results.items():
    print(f"{'PASS' if ok else 'FAIL'} {key}")
print(f"DETAIL duration={duration:.2f}s expected={expected:.2f}s pages={page_count}")
print("MANUAL REVIEW REQUIRED: headline not clipped, subtitle readability, A/V sync, pacing, Japanese spelling, claim accuracy")
raise SystemExit(0 if all(results.values()) else 1)
