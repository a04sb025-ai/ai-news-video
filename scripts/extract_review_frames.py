#!/usr/bin/env python3
"""Extract representative content frames and write the human illustration-QA checklist."""
import json
import subprocess
import sys
from pathlib import Path

video, output_dir = Path(sys.argv[1]), Path(sys.argv[2])
story_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
output_dir.mkdir(parents=True, exist_ok=True)

if story_path and story_path.is_file():
    story = json.loads(story_path.read_text())
else:
    story = {}

if story.get("explanation_contract") == "four-page-v1":
    cues = story.get("script", [])[:4]
    frames = {
        f"page-{index + 1}-mid.png": round((cue["start"] + cue["end"]) / 2, 3)
        for index, cue in enumerate(cues)
    }
else:
    frames = {"scene-2-4.5s.png": 4.5, "scene-3-7.5s.png": 7.5, "scene-4-10.5s.png": 10.5}

for name, seconds in frames.items():
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(seconds), "-i", str(video),
        "-frames:v", "1", str(output_dir / name),
    ], check=True)

checks = [
    "主役・対象・関係がニュース本文に即して具体的に見える",
    "意味のない空箱・矢印・汎用AIアイコンだけで説明していない",
    "各ページが単独でも何を伝えたいか分かる",
    "4ページを順に見ると問い→事実→争点→整理としてつながる",
    "字幕が顔・手・重要な対象を隠していない",
    "字幕がナレーション全文を読みやすく表示している",
    "4枚の画風・質感・光・彩度が揃っている",
    "スマホで見出し・補足・字幕が読める",
]
checklist = {
    "status": "human_review_required",
    "format": story.get("explanation_contract", "legacy"),
    "frames": [{"file": name, "time_seconds": seconds} for name, seconds in frames.items()],
    "illustration_checks": checks,
}
(output_dir / "illustration-review.json").write_text(json.dumps(checklist, ensure_ascii=False, indent=2) + "\n")
print("EXTRACTED " + ", ".join(frames))
print("MANUAL REVIEW REQUIRED: reports/scenes/illustration-review.json")
