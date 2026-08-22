#!/usr/bin/env python3
"""Validate display/voice separation and only the pronunciations a story uses."""
import json
import sys
from pathlib import Path

INTERNAL_KEYS = ("caption", "narration", "start", "end", "label", "subcaption")


def build_report(story):
    cues = story["script"]
    narration = "\n".join(cue["narration"] for cue in cues)
    # New stories preserve pre-normalization narration explicitly. For legacy
    # stories, captions are also source evidence that a displayed term is used.
    source = "\n".join(cue.get("source_narration", cue["narration"] + "\n" + cue.get("caption", "")) for cue in cues)
    checks = {}
    skipped = []
    for written, reading in story.get("voice_pronunciations", {}).items():
        if written not in source:
            skipped.append(written)
            continue
        checks[f"term_{written}_normalized"] = written not in narration and reading in narration
    checks["captions_do_not_expose_internal_keys"] = not any(
        key in cue.get("caption", "") for cue in cues for key in INTERNAL_KEYS
    )
    return {"checks": checks, "skipped_unused_terms": skipped, "tts_text": narration,
            "passed": all(checks.values()),
            "manual_review": "完成MP4を再生し、読みと各シーンの同期を確認する"}


def main():
    story_path, report_path = map(Path, sys.argv[1:3])
    report = build_report(json.loads(story_path.read_text()))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for name, passed in report["checks"].items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    for term in report["skipped_unused_terms"]:
        print(f"SKIP unused pronunciation term: {term}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
