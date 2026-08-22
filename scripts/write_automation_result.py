#!/usr/bin/env python3
"""Always emit the machine-readable daily automation decision."""
import json
import sys
from pathlib import Path


def read_json(path, default=None):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else ({} if default is None else default)
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {} if default is None else default


def read_text(path):
    try:
        return True, path.read_text()
    except (OSError, UnicodeError):
        return False, ""


def generated_images_ready(story, video):
    expected = story.get("image_assets", [])
    image_dir = Path(story.get("image_asset_dir", ""))
    digest = story.get("content_hash")
    correct_dir = digest and image_dir.parts[-3:] == (story.get("request_id"), digest, "daily-editorial-v1")
    files_ok = len(expected) == 4 and all(
        (image_dir / name).is_file() and (image_dir / name).stat().st_size > 0 for name in expected
    )
    log = read_json(image_dir / "image-generation-log.json")
    recorded = [entry.get("file") for entry in log.get("images", []) if isinstance(entry, dict)]
    log_ok = (log.get("status") == "complete" and log.get("content_hash") == digest
              and log.get("expected_images") == expected and recorded == expected)
    render = read_json(video.with_suffix(".render.json"))
    rendered = (render.get("used_generated_images") is True and render.get("content_hash") == digest
                and Path(render.get("image_directory", "")) == image_dir
                and render.get("images") == [str(image_dir / name) for name in expected])
    return bool(correct_dir and files_ok and log_ok and rendered)


def build_result(story, video, reports, story_valid=True):
    opening = read_json(reports / "opening" / "opening-qa.json")
    voice = read_json(reports / "voice-script-qa.json")
    qa_exists, qa_text = read_text(reports / "qa.txt")
    decode_exists, decode = read_text(reports / "decode-errors.txt")
    black_exists, black = read_text(reports / "blackdetect.txt")
    frames = opening.get("frames", [])
    checks = {
        "story_validation": bool(story_valid),
        "mp4_generated": video.is_file(),
        "video_qa": qa_exists and not any(line.startswith("FAIL") for line in qa_text.splitlines()),
        "decode_error_free": decode_exists and not decode.strip(),
        "black_frame_check": black_exists and "black_start" not in black,
        "headline_layout_qa": opening.get("passed") is True,
        "opening_frames_extracted": isinstance(frames, list) and len(frames) == 3,
        "voice_script_qa": voice.get("passed") is True,
        "size_under_25_mib": video.is_file() and video.stat().st_size <= 25 * 1024 * 1024,
    }
    success = all(checks.values())
    used = generated_images_ready(story, video) if story_valid else False
    return {"request_id": story.get("request_id", ""), "success": success,
            "auto_publish_ready": success and used, "video_file": str(video),
            "source_url": story.get("source_url", ""), "article_url": story.get("article_url", ""),
            "used_generated_images": used, "qa": checks}


def main():
    story_path, video, reports, output = map(Path, sys.argv[1:5])
    story = read_json(story_path)
    story_valid = bool(story) and all(story.get(key) for key in ("request_id", "source_url", "article_url", "content_hash"))
    if not story:
        story = read_json(story_path.parent / "source-payload.json")
    result = build_result(story, video, reports, story_valid)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
