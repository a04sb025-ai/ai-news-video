#!/usr/bin/env python3
"""Validate display/voice separation and required Japanese readings."""
import json
import re
import sys
from pathlib import Path

story_path, report_path = map(Path, sys.argv[1:3])
story = json.loads(story_path.read_text())
required = story.get("voice_pronunciations", {})
narration = "\n".join(cue["narration"] for cue in story["script"])
checks = {
    "chatgpt_reading_declared": required.get("ChatGPT") == "チャットジーピーティー",
    "chatgpt_not_sent_to_tts": not re.search(r"Chat\s*GPT", narration, re.IGNORECASE),
    "japanese_reading_sent_to_tts": "チャットジーピーティー" in narration,
    "captions_do_not_expose_internal_keys": not any(
        key in cue.get("caption", "") for cue in story["script"]
        for key in ("caption", "narration", "start", "end", "label", "subcaption")
    ),
}
report = {"checks": checks, "tts_text": narration, "passed": all(checks.values()),
          "manual_review": "完成MP4を再生し、チャットジーピーティーの読みと各シーンの同期を確認する"}
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
print("MANUAL REVIEW REQUIRED: " + report["manual_review"])
raise SystemExit(0 if report["passed"] else 1)
