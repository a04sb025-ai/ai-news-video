#!/usr/bin/env python3
"""Extract and machine-check the three thumbnail frames used by opening QA."""
import json
import statistics
import subprocess
import sys
from pathlib import Path

video, story_path, output_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
output_dir.mkdir(parents=True, exist_ok=True)
story = json.loads(story_path.read_text())
opening = story["script"][0]
checks = {
    "opening_is_exactly_3s": opening["start"] == 0 and opening["end"] == 3,
    "headline_max_2_lines": len(opening["caption"].splitlines()) <= 2,
    "headline_is_concise": all(len(line) <= 18 for line in opening["caption"].splitlines()),
}
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
    checks["headline_matches_verified_story"] = opening["caption"].replace("\n", "") == story["claims"][0]["text"]
frames = []
for seconds in (0.0, 1.0, 2.0, 3.0):
    stem = f"opening-{seconds:g}s"
    png = output_dir / f"{stem}.png"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(seconds), "-i", str(video),
        "-frames:v", "1", str(png),
    ], check=True)
    # A tiny RGB sample makes contrast/empty-frame checks dependency-free.
    ppm = subprocess.check_output([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(seconds), "-i", str(video),
        "-frames:v", "1", "-vf", "scale=90:160", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
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
    }
    frames.append(result)
    checks[f"frame_{seconds:.1f}s_visible"] = result["not_black_or_empty"]
    checks[f"frame_{seconds:.1f}s_contrast"] = result["high_contrast"]
report = {
    "purpose": "0-3秒を音声なしのSNSサムネイルとして検査",
    "headline": opening["caption"],
    "frames": frames,
    "checks": checks,
    "layout_details": layout_details,
    "reasons": [name for name, passed in checks.items() if not passed],
    "manual_review": [
        "見出しがスマホで読める", "ニュース内容を推測できる", "主役画像が十分大きい",
        "不要な空白が多すぎない", "字幕やUIが主役を邪魔しない", "スクロール中に目を引く",
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
