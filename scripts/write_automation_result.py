#!/usr/bin/env python3
"""Combine daily render evidence into the machine-readable automation decision."""
import json, sys
from pathlib import Path
story_path, video, reports, output = map(Path, sys.argv[1:5])
story = json.loads(story_path.read_text())
opening = json.loads((reports / "opening" / "opening-qa.json").read_text())
voice = json.loads((reports / "voice-script-qa.json").read_text())
image_dir = Path(story["image_asset_dir"]); used = all((image_dir / name).is_file() for name in story["image_assets"])
checks = {
 "story_validation": True, "mp4_generated": video.is_file(), "video_qa": (reports / "qa.txt").is_file(),
 "decode_error_free": not (reports / "decode-errors.txt").read_text().strip(),
 "black_frame_check": "black_start" not in (reports / "blackdetect.txt").read_text(),
 "headline_layout_qa": opening["passed"], "opening_frames_extracted": len(opening["frames"]) == 3,
 "voice_script_qa": voice["passed"], "size_under_25_mib": video.stat().st_size <= 25 * 1024 * 1024,
}
success = all(checks.values())
result = {"request_id": story["request_id"], "success": success,
 "auto_publish_ready": success and used, "video_file": str(video), "source_url": story["source_url"],
 "article_url": story["article_url"], "used_generated_images": used, "qa": checks}
output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
print(json.dumps(result, ensure_ascii=False)); raise SystemExit(0 if success else 1)
