#!/usr/bin/env python3
"""Bounded, deterministic recovery loop for daily AI-news video rendering.

The loop never weakens QA and never rewrites verified facts. It only retries
recoverable media/layout failures, regenerates missing cached illustrations when
an API key is available, and applies a size-only transcode when needed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_REPAIRS = int(os.environ.get("SELF_HEAL_MAX_REPAIRS", "2"))


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}


def run(command: list[str], *, env: dict | None = None, log: Path | None = None) -> int:
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(completed.stdout or "")
    else:
        sys.stdout.write(completed.stdout or "")
    return completed.returncode


def archive_attempt(reports: Path, number: int, label: str) -> None:
    target = reports / "self-heal" / f"attempt-{number}-{label}"
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        "automation-result.json", "qa.txt", "video-qa.json", "video-qa.txt",
        "voice-script-qa.json", "voice-script-qa.txt", "opening-qa.txt",
        "image-generation.txt",
    ):
        source = reports / name
        if source.is_file():
            shutil.copy2(source, target / name)
    opening = reports / "opening"
    if opening.is_dir():
        shutil.copytree(opening, target / "opening", dirs_exist_ok=True)


def optimize_if_needed(video: Path) -> bool:
    if not video.is_file() or video.stat().st_size <= 24 * 1024 * 1024:
        return False
    temporary = video.with_name(f".{video.stem}.compressed{video.suffix}")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-c:v", "libx264", "-crf", "27", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(temporary),
    ], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(temporary), "-f", "null", "-"], check=True)
    temporary.replace(video)
    return True


def regenerate_images_if_needed(story: Path, result: dict, reports: Path) -> bool:
    if result.get("used_generated_images") is True:
        return False
    if not os.environ.get("OPENAI_API_KEY"):
        return False
    status = run(
        [sys.executable, "scripts/generate_story_images.py", str(story)],
        log=reports / "image-generation-self-heal.txt",
    )
    return status == 0


def perform_qa(story: Path, video: Path, reports: Path) -> dict:
    opening = reports / "opening"
    scenes = reports / "scenes"
    opening.mkdir(parents=True, exist_ok=True)
    scenes.mkdir(parents=True, exist_ok=True)

    run([sys.executable, "scripts/check_story_voice.py", str(story), str(reports / "voice-script-qa.json")],
        log=reports / "voice-script-qa.txt")
    run([sys.executable, "scripts/check_opening_frames.py", str(video), str(story), str(opening)],
        log=reports / "opening-qa.txt")
    run([sys.executable, "scripts/extract_review_frames.py", str(video), str(scenes)])
    run([sys.executable, "scripts/check_video.py", str(video)], log=reports / "qa.txt")
    run([sys.executable, "scripts/run_video_qa.py", str(video), str(reports)])
    run([
        sys.executable, "scripts/write_automation_result.py", str(story), str(video),
        str(reports), str(reports / "automation-result.json"),
    ])
    return read_json(reports / "automation-result.json")


def is_semantic_stop(result: dict) -> bool:
    qa = result.get("qa", {})
    if qa.get("story_validation") is False or qa.get("voice_script_qa") is False:
        return True
    details = result.get("qa_details", {}).get("headline_layout_qa", {})
    reason = str(details.get("reason", ""))
    return "headline_matches_verified_story" in reason


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: self_heal_daily_video.py STORY_JSON VIDEO_MP4 REPORTS_DIR")
    story, video, reports = map(Path, sys.argv[1:4])
    result_path = reports / "automation-result.json"
    reports.mkdir(parents=True, exist_ok=True)
    result = read_json(result_path)
    attempts: list[dict] = []

    if result.get("auto_publish_ready") is True:
        summary = {"status": "ready", "repairs": 0, "attempts": [], "final": result}
        (reports / "self-heal-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        return 0

    for repair in range(1, MAX_REPAIRS + 1):
        if is_semantic_stop(result):
            attempts.append({"repair": repair, "action": "stopped", "reason": "semantic-or-voice-gate"})
            break

        archive_attempt(reports, repair, "before")
        regenerated = regenerate_images_if_needed(story, result, reports)
        env = dict(os.environ)
        env["OPENING_SAFE_MODE"] = "1"

        video.unlink(missing_ok=True)
        video.with_suffix(".render.json").unlink(missing_ok=True)
        render_status = run([sys.executable, "scripts/render_reference.py", str(story), str(video)], env=env,
                            log=reports / f"self-heal-render-{repair}.txt")
        if render_status != 0 or not video.is_file():
            attempts.append({"repair": repair, "action": "rerender", "rendered": False, "regenerated_images": regenerated})
            continue

        compressed = optimize_if_needed(video)
        result = perform_qa(story, video, reports)
        ready = result.get("auto_publish_ready") is True
        attempts.append({
            "repair": repair,
            "action": "safe-rerender",
            "rendered": True,
            "regenerated_images": regenerated,
            "compressed": compressed,
            "auto_publish_ready": ready,
            "failed_checks": [name for name, passed in result.get("qa", {}).items() if not passed],
        })
        archive_attempt(reports, repair, "after")
        if ready:
            break

    final = read_json(result_path)
    ready = final.get("auto_publish_ready") is True
    summary = {
        "status": "ready" if ready else "needs-human-review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repairs": len(attempts),
        "attempts": attempts,
        "final": final,
        "policy": "Never bypass story, voice, headline-truth, or media QA gates.",
    }
    (reports / "self-heal-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
