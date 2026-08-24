#!/usr/bin/env python3
import json
import sys
from pathlib import Path
import write_automation_result as base

def main():
    story_path, video, reports, output = map(Path, sys.argv[1:5])
    story = base.read_json(story_path)
    story_valid = bool(story) and all(story.get(key) for key in ("request_id", "source_url", "article_url", "content_hash"))
    result = base.build_result(story, video, reports, story_valid)
    render = base.read_json(video.with_suffix(".render.json"))
    adaptive_ok = bool(
        story.get("explanation_contract") == "adaptive-pages-v1"
        and render.get("renderer") == "adaptive-explainer-v1"
        and render.get("full_narration_subtitles") is True
        and int(render.get("subtitle_font_size_px", 0)) >= 48
        and int(render.get("opening_headline_target_chars_per_line", 99)) <= 10
    )
    result.setdefault("qa", {})["adaptive_explainer_renderer_used"] = adaptive_ok
    result["success"] = all(result["qa"].values())
    result["auto_publish_ready"] = result["success"] and result.get("used_generated_images") is True
    result.setdefault("qa_details", {})["adaptive_readability_qa"] = {
        "passed": adaptive_ok,
        "reason": "adaptive readability evidence confirmed" if adaptive_ok else "adaptive readability evidence missing",
        "details": {
            "renderer": render.get("renderer"),
            "subtitle_font_size_px": render.get("subtitle_font_size_px"),
            "opening_headline_target_chars_per_line": render.get("opening_headline_target_chars_per_line"),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["success"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
