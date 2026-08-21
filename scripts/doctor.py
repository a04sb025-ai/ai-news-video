#!/usr/bin/env python3
import json
import shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "config/short-ja.json").read_text())
checks = {"python": bool(shutil.which("python3")), "ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")), "openmontage": (ROOT / "vendor/openmontage/README.md").is_file(), "vertical_config": config["canvas"] == {"width": 1080, "height": 1920, "fps": 30}}
for name, ok in checks.items():
    print(f"{'OK' if ok else 'MISSING'}  {name}")
raise SystemExit(0 if all(checks.values()) else 1)
