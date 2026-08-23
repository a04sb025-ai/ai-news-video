#!/usr/bin/env python3
"""Validate display/voice separation, pronunciation normalization, and subtitle completeness."""
import json
import sys
from pathlib import Path

INTERNAL_KEYS = ("caption", "narration", "start", "end", "label", "subcaption")


def compact(text):
    return "".join(str(text).split())


def build_report(story):
    cues = story["script"]
    narration = "\n".join(cue["narration"] for cue in cues)
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
    if story.get("explanation_contract") == "four-page-v1":
        pages = cues[:4]
        checks["all_four_pages_have_subtitles"] = len(pages) == 4 and all(bool(cue.get("subtitle", "").strip()) for cue in pages)
        checks["subtitles_cover_full_narration"] = len(pages) == 4 and all(
            compact(cue.get("subtitle", "")) == compact(cue.get("source_narration", "")) for cue in pages
        )
        checks["support_text_present_on_all_pages"] = len(pages) == 4 and all(bool(cue.get("support_text", "").strip()) for cue in pages)
    return {"checks": checks, "skipped_unused_terms": skipped, "tts_text": narration,
            "passed": all(checks.values()),
            "manual_review": "完成MP4を再生し、読み・字幕全文・各シーンの同期を確認する"}


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
