#!/usr/bin/env python3
import json, shutil, subprocess, sys
from pathlib import Path

video = Path(sys.argv[1])
story_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
story = {}
if story_path and story_path.is_file():
    try:
        story = json.loads(story_path.read_text())
    except (OSError, json.JSONDecodeError):
        story = {}

# Some workflow callers intentionally pass only the MP4. In that case, infer the
# duration contract from the renderer's sidecar instead of falsely failing every
# valid four-page explainer and needlessly invoking self-heal.
render_manifest = {}
manifest_path = video.with_suffix(".render.json")
if manifest_path.is_file():
    try:
        render_manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        render_manifest = {}
is_four_page = (
    story.get("explanation_contract") == "four-page-v1"
    or render_manifest.get("renderer") == "four-page-explainer-v1"
)

ffprobe = shutil.which("ffprobe") or "ffprobe"
cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(video)]
try:
    info = json.loads(subprocess.check_output(cmd, text=True))
except (FileNotFoundError, subprocess.CalledProcessError) as exc:
    raise SystemExit(f"ffprobe failed: {exc}")
vstream = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
duration = float(info["format"]["duration"])
if is_four_page:
    duration_key, duration_ok = "duration_18_22s", 18 <= duration <= 22
else:
    duration_key, duration_ok = "duration_10_15s", 10 <= duration <= 15
results = {
    duration_key: duration_ok,
    "resolution_1080x1920": (vstream.get("width"), vstream.get("height")) == (1080, 1920),
    "audio_present": any(s.get("codec_type") == "audio" for s in info["streams"]),
}
for key, ok in results.items():
    print(f"{'PASS' if ok else 'FAIL'} {key}")
print("MANUAL REVIEW REQUIRED: black/frozen frames, caption safe area/readability, A/V sync, loudness, Japanese spelling, and claim accuracy")
raise SystemExit(0 if all(results.values()) else 1)
