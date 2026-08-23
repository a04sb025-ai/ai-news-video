#!/usr/bin/env python3
"""Extract and machine-check the four thumbnail frames used by opening QA."""
import json
import hashlib
import statistics
import subprocess
import sys
from pathlib import Path


FPS = 30
QA_FRAME_SIZE = (270, 480)
OPENING_REGIONS = {
    "headline": (90, 190, 990, 600),
    "panel": (42, 150, 1038, 660),
    "visual": (82, 700, 998, 1270),
    "mozo": (75, 1360, 450, 1785),
    "bubble": (390, 1370, 950, 1550),
}


def opening_sample_seconds(opening_duration, fps):
    """Return samples inside [0, opening_duration), including its final frame."""
    if opening_duration <= 0 or fps <= 0:
        raise ValueError("opening duration and fps must be positive")
    last_frame = opening_duration - (1 / fps)
    whole_seconds = [float(second) for second in range(3) if second <= last_frame]
    if not whole_seconds or abs(whole_seconds[-1] - last_frame) > 1e-9:
        whole_seconds.append(last_frame)
    return whole_seconds


def timestamp_label(seconds):
    return f"{seconds:.3f}".rstrip("0").rstrip(".")


def normalize_layout_text(text):
    """Ignore layout-only whitespace while preserving all semantic characters."""
    return "".join(str(text).split())


def region_metrics(rgb, width, height, region):
    """Measure whether a named opening region contains visible pixels."""
    source_width, source_height = 1080, 1920
    left, top, right, bottom = region
    left, right = round(left * width / source_width), round(right * width / source_width)
    top, bottom = round(top * height / source_height), round(bottom * height / source_height)
    luminance = []
    for y in range(top, bottom):
        for x in range(left, right):
            offset = (y * width + x) * 3
            luminance.append(round(.2126 * rgb[offset] + .7152 * rgb[offset + 1] + .0722 * rgb[offset + 2]))
    mean = statistics.fmean(luminance)
    contrast = statistics.pstdev(luminance)
    near_black = sum(value < 12 for value in luminance) / len(luminance)
    return {
        "mean_luma": round(mean, 2),
        "luma_contrast": round(contrast, 2),
        "near_black_ratio": round(near_black, 4),
        "visible": 12 <= mean <= 245 and near_black < .9,
    }


video, story_path, output_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
output_dir.mkdir(parents=True, exist_ok=True)
story = json.loads(story_path.read_text())
opening = story["script"][0]
checks = {
    "opening_is_exactly_3s": opening["start"] == 0 and opening["end"] == 3,
    "headline_max_2_lines": len(opening["caption"].splitlines()) <= 2,
    "headline_is_concise": all(len(line) <= 18 for line in opening["caption"].splitlines()),
}
if "content_hash" in story:
    reference = Path(story.get("opening", {}).get("character_reference", ""))
    opening_asset = Path(story.get("opening", {}).get("character_asset", ""))
    render_manifest_path = video.with_suffix(".render.json")
    try:
        render_manifest = json.loads(render_manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        render_manifest = {}
    try:
        opening_asset_digest = hashlib.sha256(opening_asset.read_bytes()).hexdigest()
        opening_asset_is_png = opening_asset.stat().st_size > 64 and opening_asset.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    except OSError:
        opening_asset_digest, opening_asset_is_png = "", False
    checks.update({
        "visual_standard_is_current": story.get("visual_standard") == "ai-news-visual-v1",
        "template_is_supported": story.get("visual_template", {}).get("id") in {"A", "B", "C"},
        "mozo_is_standard_character": story.get("opening", {}).get("character") == "mozo",
        "major_elements_static_for_full_opening": story.get("opening", {}).get("major_elements_static") is True,
        "official_mozo_reference_declared": str(reference) == "assets/visual-references/mozo/mozo-character-reference.png",
        "approved_mozo_opening_asset_declared": str(opening_asset) == "assets/visual-references/mozo/mozo-opening.png",
        "approved_mozo_opening_asset_is_readable_png": opening_asset_is_png,
        "renderer_used_approved_mozo_opening_asset": render_manifest.get("used_mozo_opening_asset") is True,
        "rendered_mozo_opening_asset_hash_matches": bool(opening_asset_digest) and render_manifest.get("mozo_opening_asset_sha256") == opening_asset_digest,
    })
layout_details = {
    "line_count": len(opening["caption"].splitlines()), "maximum_lines": 2,
    "maximum_characters_per_line": max(map(len, opening["caption"].splitlines()), default=0),
    "required_maximum_characters_per_line": 18, "font_size_px": 112,
    "required_minimum_font_size_px": 56,
    "safe_area_px": {"left": 90, "right": 90, "top": 160, "bottom": 260},
    "headline_box_px": {"left": 112, "top": 255, "right": 990, "bottom": 565},
}
if "request_id" not in story:
    checks["headline_is_present"] = bool(opening["caption"].strip())
else:
    checks["headline_matches_verified_story"] = (
        normalize_layout_text(opening["caption"])
        == normalize_layout_text(story["claims"][0]["text"])
    )
frames = []
opening_duration = opening["end"] - opening["start"]
for seconds in opening_sample_seconds(opening_duration, FPS):
    label = timestamp_label(seconds)
    stem = f"opening-{label}s"
    png = output_dir / f"{stem}.png"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(seconds), "-i", str(video),
        "-frames:v", "1", str(png),
    ], check=True)
    # A tiny RGB sample makes contrast/empty-frame checks dependency-free.
    ppm = subprocess.check_output([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(seconds), "-i", str(video),
        "-frames:v", "1", "-vf", f"scale={QA_FRAME_SIZE[0]}:{QA_FRAME_SIZE[1]}",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])
    luminance = [round(.2126 * ppm[i] + .7152 * ppm[i + 1] + .0722 * ppm[i + 2]) for i in range(0, len(ppm), 3)]
    mean = statistics.fmean(luminance)
    contrast = statistics.pstdev(luminance)
    dark = sum(value < 12 for value in luminance) / len(luminance)
    bright = sum(value > 220 for value in luminance) / len(luminance)
    result = {
        "time_seconds": seconds, "file": str(png), "mean_luma": round(mean, 2),
        "luma_contrast": round(contrast, 2), "near_black_ratio": round(dark, 4),
        "bright_ratio": round(bright, 4),
        "not_black_or_empty": 20 <= mean <= 235 and dark < .75,
        "high_contrast": contrast >= 22,
        "regions": {
            name: region_metrics(ppm, *QA_FRAME_SIZE, bounds)
            for name, bounds in OPENING_REGIONS.items()
        },
    }
    frames.append(result)
    checks[f"frame_{label}s_visible"] = result["not_black_or_empty"]
    checks[f"frame_{label}s_contrast"] = result["high_contrast"]
    for name, metrics in result["regions"].items():
        checks[f"frame_{label}s_{name}_visible"] = metrics["visible"]
report = {
    "purpose": "0-3秒を音声なしのSNSサムネイルとして検査",
    "headline": opening["caption"],
    "frames": frames,
    "checks": checks,
    "layout_details": layout_details,
    "reasons": [name for name, passed in checks.items() if not passed],
    "manual_review": [
        "見出しがスマホで読め、safe area内にある", "ニュース内容を推測できる", "中央カードが1メッセージを示す",
        "もぞが白目なし・左右非対称の既定デザインで、ニュースを邪魔しない", "背景が見出しを邪魔しない",
        "0秒・1秒・2秒・opening最終フレームのどれも単独サムネイルとして成立する",
    ],
    "passed": all(checks.values()),
}
(output_dir / "opening-qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
print("QA: headline_layout_qa")
print(f"RESULT: {'PASS' if report['passed'] else 'FAIL'}")
print("REASON: " + ("all headline layout rules passed" if report["passed"] else "; ".join(report["reasons"])))
print("DETAIL: " + json.dumps(layout_details, ensure_ascii=False))
print("MANUAL REVIEW REQUIRED: " + " / ".join(report["manual_review"]))
raise SystemExit(0 if report["passed"] else 1)
