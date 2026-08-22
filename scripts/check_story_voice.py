#!/usr/bin/env python3
"""Validate display/voice separation and declared pronunciation replacements."""
import json, sys
from pathlib import Path
story_path, report_path = map(Path, sys.argv[1:3]); story = json.loads(story_path.read_text())
terms = story.get("voice_pronunciations", {}); narration = "\n".join(c["narration"] for c in story["script"])
checks = {f"term_{written}_normalized": written not in narration and reading in narration for written, reading in terms.items()}
checks["captions_do_not_expose_internal_keys"] = not any(key in cue.get("caption", "") for cue in story["script"] for key in ("caption", "narration", "start", "end", "label", "subcaption"))
report = {"checks": checks, "tts_text": narration, "passed": all(checks.values()), "manual_review": "完成MP4を再生し、読みと各シーンの同期を確認する"}
report_path.parent.mkdir(parents=True, exist_ok=True); report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
for name, passed in checks.items(): print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if report["passed"] else 1)
