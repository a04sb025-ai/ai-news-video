#!/usr/bin/env python3
"""Bounded recovery loop for adaptive daily AI-news explainers."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import self_heal_daily_video as base

RENDERER = "scripts/render_adaptive_explainer.py"
MAX_REPAIRS = int(os.environ.get("SELF_HEAL_MAX_REPAIRS", "2"))


def failed_checks(result: dict) -> list[str]:
    return [name for name, passed in result.get("qa", {}).items() if passed is not True]


def publish_blockers(result: dict) -> list[str]:
    explicit = result.get("publish_blockers")
    if isinstance(explicit, list):
        return [str(value) for value in explicit if str(value)]
    blockers = [f"qa:{name}" for name in failed_checks(result)]
    if result.get("success") is True and result.get("auto_publish_ready") is not True and not blockers:
        blockers.append("publish_gate_unspecified")
    return blockers


def result_is_complete(result: dict) -> bool:
    return isinstance(result.get("qa"), dict) and bool(result.get("qa")) and "success" in result


def publish_only_retryable(result: dict, attempts: list[dict], has_image_key: bool) -> bool:
    """Only retry a publish-only block when image generation can still change the result."""
    if failed_checks(result):
        return True
    blockers = publish_blockers(result)
    if blockers != ["generated_images_not_ready"] or not has_image_key:
        return False
    for attempt in attempts:
        if attempt.get("regenerated_images") is True and attempt.get("publish_blockers") == blockers:
            return False
    return True


def perform_qa(story: Path, video: Path, reports: Path) -> dict:
    opening = reports / "opening"
    scenes = reports / "scenes"
    opening.mkdir(parents=True, exist_ok=True)
    scenes.mkdir(parents=True, exist_ok=True)

    base.run([sys.executable, "scripts/check_story_voice.py", str(story), str(reports / "voice-script-qa.json")],
             log=reports / "voice-script-qa.txt")
    base.run([sys.executable, "scripts/check_opening_frames.py", str(video), str(story), str(opening)],
             log=reports / "opening-qa.txt")
    base.run([sys.executable, "scripts/extract_review_frames.py", str(video), str(scenes), str(story)])
    base.run([sys.executable, "scripts/check_adaptive_video.py", str(video), str(story)], log=reports / "qa.txt")
    base.run([sys.executable, "scripts/run_video_qa.py", str(video), str(reports)])
    base.run([
        sys.executable, "scripts/write_adaptive_result.py", str(story), str(video),
        str(reports), str(reports / "automation-result.json"),
    ])
    return base.read_json(reports / "automation-result.json")


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: self_heal_adaptive_daily_video.py STORY_JSON VIDEO_MP4 REPORTS_DIR")
    story, video, reports = map(Path, sys.argv[1:4])
    reports.mkdir(parents=True, exist_ok=True)
    result = base.read_json(reports / "automation-result.json")
    attempts = []
    has_image_key = bool(os.environ.get("OPENAI_API_KEY"))

    if result.get("auto_publish_ready") is True:
        summary = {
            "status": "ready",
            "repairs": 0,
            "attempts": [],
            "failed_checks": [],
            "publish_blockers": [],
            "final": result,
        }
        (reports / "self-heal-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        return 0

    for repair in range(1, MAX_REPAIRS + 1):
        if base.is_semantic_stop(result):
            attempts.append({
                "repair": repair,
                "action": "stopped",
                "reason": "semantic-or-voice-gate",
                "failed_checks": failed_checks(result),
                "publish_blockers": publish_blockers(result),
            })
            break

        if result_is_complete(result) and not publish_only_retryable(result, attempts, has_image_key):
            attempts.append({
                "repair": repair,
                "action": "stopped",
                "reason": "non-repairable-publish-gate",
                "failed_checks": failed_checks(result),
                "publish_blockers": publish_blockers(result),
            })
            break

        base.archive_attempt(reports, repair, "before")
        regenerated = base.regenerate_images_if_needed(story, result, reports)
        env = dict(os.environ)
        env["OPENING_SAFE_MODE"] = "1"

        video.unlink(missing_ok=True)
        video.with_suffix(".render.json").unlink(missing_ok=True)
        render_status = base.run([sys.executable, RENDERER, str(story), str(video)], env=env,
                                 log=reports / f"self-heal-render-{repair}.txt")
        if render_status != 0 or not video.is_file():
            attempts.append({
                "repair": repair,
                "action": "rerender",
                "renderer": RENDERER,
                "rendered": False,
                "regenerated_images": regenerated,
                "failed_checks": failed_checks(result),
                "publish_blockers": publish_blockers(result),
            })
            continue

        compressed = base.optimize_if_needed(video)
        result = perform_qa(story, video, reports)
        ready = result.get("auto_publish_ready") is True
        attempts.append({
            "repair": repair,
            "action": "safe-rerender",
            "renderer": RENDERER,
            "rendered": True,
            "regenerated_images": regenerated,
            "compressed": compressed,
            "auto_publish_ready": ready,
            "failed_checks": failed_checks(result),
            "publish_blockers": publish_blockers(result),
        })
        base.archive_attempt(reports, repair, "after")
        if ready:
            break

    final = base.read_json(reports / "automation-result.json")
    ready = final.get("auto_publish_ready") is True
    final_failed = failed_checks(final)
    final_blockers = publish_blockers(final)
    repair_count = sum(1 for attempt in attempts if attempt.get("action") in {"rerender", "safe-rerender"})
    status = "ready" if ready else ("blocked-publish-gate" if final.get("success") is True else "failed-qa")
    summary = {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repairs": repair_count,
        "attempts": attempts,
        "failed_checks": final_failed,
        "publish_blockers": final_blockers,
        "final": final,
        "policy": "Never bypass factual, voice, headline, readability, subtitle-completeness, generated-image, or media QA gates.",
    }
    (reports / "self-heal-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
