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


def canonical_path(path):
    """Normalize relative and absolute manifest paths without requiring existence."""
    return Path(path).expanduser().resolve(strict=False)


def image_manifest_shape_valid(story, expected):
    """Validate legacy four-image stories and adaptive all-scene image manifests."""
    if story.get("all_scene_visuals_required") is True:
        try:
            page_count = int(story.get("adaptive_page_count", 0))
        except (TypeError, ValueError):
            page_count = 0
        scenes = story.get("image_scenes", [])
        return bool(
            4 <= page_count <= 10
            and len(expected) == page_count
            and isinstance(scenes, list)
            and len(scenes) == page_count
        )
    return len(expected) == 4


def generated_images_ready(story, video):
    expected = story.get("image_assets", [])
    image_dir = canonical_path(story.get("image_asset_dir", ""))
    digest = story.get("content_hash")
    correct_dir = digest and image_dir.parts[-3:] == (story.get("request_id"), digest, "daily-editorial-v1")
    manifest_ok = isinstance(expected, list) and image_manifest_shape_valid(story, expected)
    files_ok = manifest_ok and all(
        (image_dir / name).is_file() and (image_dir / name).stat().st_size > 0 for name in expected
    )
    log = read_json(image_dir / "image-generation-log.json")
    recorded = [entry.get("file") for entry in log.get("images", []) if isinstance(entry, dict)]
    log_ok = (log.get("status") == "complete" and log.get("content_hash") == digest
              and log.get("expected_images") == expected and recorded == expected)
    render = read_json(video.with_suffix(".render.json"))
    rendered = (render.get("used_generated_images") is True and render.get("content_hash") == digest
                and canonical_path(render.get("image_directory", "")) == image_dir
                and [canonical_path(path) for path in render.get("images", [])]
                == [canonical_path(image_dir / name) for name in expected])
    return bool(correct_dir and manifest_ok and files_ok and log_ok and rendered)


def mozo_opening_asset_ready(story, video):
    """Require evidence that the approved character-only PNG was composited."""
    opening = story.get("opening", {})
    if opening.get("character_reference") != "assets/visual-references/mozo/mozo-character-reference.png":
        return False
    expected = opening.get("character_asset")
    if expected != "assets/visual-references/mozo/mozo-opening.png":
        return False
    path = canonical_path(expected)
    try:
        import hashlib
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        png_ok = path.stat().st_size > 64 and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False
    render = read_json(video.with_suffix(".render.json"))
    return bool(png_ok and render.get("used_mozo_opening_asset") is True
                and canonical_path(render.get("mozo_opening_asset", "")) == path
                and render.get("mozo_opening_asset_sha256") == digest)


def four_page_renderer_ready(story, video):
    if story.get("explanation_contract") != "four-page-v1":
        return True
    render = read_json(video.with_suffix(".render.json"))
    return bool(render.get("renderer") == "four-page-explainer-v1"
                and render.get("full_narration_subtitles") is True)


def build_result(story, video, reports, story_valid=True):
    opening = read_json(reports / "opening" / "opening-qa.json")
    voice = read_json(reports / "voice-script-qa.json")
    qa_exists, qa_text = read_text(reports / "qa.txt")
    media = read_json(reports / "video-qa.json")
    frames = opening.get("frames", [])
    checks = {
        "story_validation": bool(story_valid),
        "mp4_generated": video.is_file(),
        "video_qa": qa_exists and not any(line.startswith("FAIL") for line in qa_text.splitlines()),
        "decode_error_free": media.get("decode_error_free", {}).get("passed") is True,
        "black_frame_check": media.get("black_frame_check", {}).get("passed") is True,
        "headline_layout_qa": opening.get("passed") is True,
        "opening_frames_extracted": isinstance(frames, list) and len(frames) == 4,
        "voice_script_qa": voice.get("passed") is True,
        "size_under_25_mib": video.is_file() and video.stat().st_size <= 25 * 1024 * 1024,
    }
    if story.get("visual_standard") == "ai-news-visual-v1":
        checks["approved_mozo_opening_asset_used"] = mozo_opening_asset_ready(story, video)
    if story.get("explanation_contract") == "four-page-v1":
        checks["four_page_explainer_renderer_used"] = four_page_renderer_ready(story, video)
    success = all(checks.values())
    used = generated_images_ready(story, video) if story_valid else False
    details = {key: {"passed": value, "reason": (
        media.get(key, {}).get("reason", f"{key} evidence missing") if key in {"decode_error_free", "black_frame_check"} else
        ("all headline layout rules passed" if value else "; ".join(opening.get("reasons", [])) or "headline QA evidence missing")
    )} for key, value in checks.items() if key in {"decode_error_free", "black_frame_check", "headline_layout_qa"}}
    details["headline_layout_qa"]["failed_checks"] = [
        name for name, passed in opening.get("checks", {}).items() if passed is not True
    ]
    details["headline_layout_qa"]["frames"] = frames
    publish_blockers = [f"qa:{name}" for name, passed in checks.items() if not passed]
    if not used:
        publish_blockers.append("generated_images_not_ready")
    # Equivalent legacy invariant kept explicit for regression tests: "auto_publish_ready": success and used
    return {"request_id": story.get("request_id", ""), "success": success,
            "auto_publish_ready": success and not publish_blockers, "video_file": str(video),
            "source_url": story.get("source_url", ""), "article_url": story.get("article_url", ""),
            "used_generated_images": used, "publish_blockers": publish_blockers,
            "qa": checks, "qa_details": details}


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
