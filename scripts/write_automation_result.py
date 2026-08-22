#!/usr/bin/env python3
"""Combine daily render evidence into the machine-readable automation decision."""
import json
import sys
from pathlib import Path


def generated_images_ready(story, video):
    expected = story.get("image_assets", [])
    image_dir = Path(story.get("image_asset_dir", ""))
    digest = story.get("content_hash")
    correct_dir = digest and image_dir.parts[-3:] == (story.get("request_id"), digest, "daily-editorial-v1")
    files_ok = len(expected) == 4 and all(
        (image_dir / name).is_file() and (image_dir / name).stat().st_size > 0 for name in expected
    )
    log_path = image_dir / "image-generation-log.json"
    try:
        log = json.loads(log_path.read_text())
    except (OSError, json.JSONDecodeError):
        log = {}
    recorded = [entry.get("file") for entry in log.get("images", [])]
    log_ok = (log.get("status") == "complete" and log.get("content_hash") == digest
              and log.get("expected_images") == expected and recorded == expected)
    try:
        render = json.loads(video.with_suffix(".render.json").read_text())
    except (OSError, json.JSONDecodeError):
        render = {}
    rendered = (render.get("used_generated_images") is True and render.get("content_hash") == digest
                and Path(render.get("image_directory", "")) == image_dir
                and render.get("images") == [str(image_dir / name) for name in expected])
    return bool(correct_dir and files_ok and log_ok and rendered)


def build_result(story, video, reports):
    opening = json.loads((reports / "opening" / "opening-qa.json").read_text())
    voice = json.loads((reports / "voice-script-qa.json").read_text())
    checks = {
        "story_validation": True,
        "mp4_generated": video.is_file(),
        "video_qa": (reports / "qa.txt").is_file(),
        "decode_error_free": not (reports / "decode-errors.txt").read_text().strip(),
        "black_frame_check": "black_start" not in (reports / "blackdetect.txt").read_text(),
        "headline_layout_qa": opening["passed"],
        "opening_frames_extracted": len(opening["frames"]) == 3,
        "voice_script_qa": voice["passed"],
        "size_under_25_mib": video.is_file() and video.stat().st_size <= 25 * 1024 * 1024,
    }
    success = all(checks.values())
    used = generated_images_ready(story, video)
    return {"request_id": story["request_id"], "success": success,
            "auto_publish_ready": success and used, "video_file": str(video),
            "source_url": story["source_url"], "article_url": story["article_url"],
            "used_generated_images": used, "qa": checks}


def main():
    story_path, video, reports, output = map(Path, sys.argv[1:5])
    story = json.loads(story_path.read_text())
    result = build_result(story, video, reports)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
