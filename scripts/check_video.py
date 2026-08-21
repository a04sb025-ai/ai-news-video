#!/usr/bin/env python3
import json, shutil, subprocess, sys
from pathlib import Path
video = Path(sys.argv[1])
ffprobe = shutil.which("ffprobe") or "ffprobe"
cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(video)]
try:
    info = json.loads(subprocess.check_output(cmd, text=True))
except (FileNotFoundError, subprocess.CalledProcessError) as exc:
    raise SystemExit(f"ffprobe failed: {exc}")
vstream = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
duration = float(info["format"]["duration"])
results = {"duration_10_15s": 10 <= duration <= 15, "resolution_1080x1920": (vstream.get("width"), vstream.get("height")) == (1080, 1920), "audio_present": any(s.get("codec_type") == "audio" for s in info["streams"])}
for key, ok in results.items():
    print(f"{'PASS' if ok else 'FAIL'} {key}")
print("MANUAL REVIEW REQUIRED: black/frozen frames, caption safe area/readability, A/V sync, loudness, Japanese spelling, and claim accuracy")
raise SystemExit(0 if all(results.values()) else 1)
