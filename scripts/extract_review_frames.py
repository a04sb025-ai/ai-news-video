#!/usr/bin/env python3
"""Extract representative content frames and write the human illustration-QA checklist."""
import json
import subprocess
import sys
from pathlib import Path

video, output_dir = Path(sys.argv[1]), Path(sys.argv[2])
output_dir.mkdir(parents=True, exist_ok=True)
frames = {"scene-2-4.5s.png": 4.5, "scene-3-7.5s.png": 7.5, "scene-4-10.5s.png": 10.5}
for name, seconds in frames.items():
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(seconds), "-i", str(video),
        "-frames:v", "1", str(output_dir / name),
    ], check=True)
checklist = {
    "status": "human_review_required",
    "frames": [{"file": name, "time_seconds": seconds} for name, seconds in frames.items()],
    "illustration_checks": [
        "AIロボットが主役になっていない", "主役が人物になっている",
        "教材・ストック・プレゼン資料風ではない", "人物に自然な表情と個性がある",
        "AIをUIと人物の行動で表現している", "画像だけでも各シーンの意味を推測できる",
        "字幕が顔・手・デバイスを隠していない", "4枚の画風・人物・質感・光・彩度が揃っている",
        "スマホで魅力がある", "生成AIの説明画像という第一印象が弱い",
    ],
}
(output_dir / "illustration-review.json").write_text(json.dumps(checklist, ensure_ascii=False, indent=2) + "\n")
print("EXTRACTED " + ", ".join(frames))
print("MANUAL REVIEW REQUIRED: reports/scenes/illustration-review.json")
