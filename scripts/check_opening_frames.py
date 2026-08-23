#!/usr/bin/env python3
"""Extract and machine-check the three thumbnail frames used by opening QA."""
import json
import statistics
import subprocess
import sys
from pathlib import Path


FPS = 30


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


def pixel_metrics(rgb):
    luminance = [round(.2126 * rgb[i] + .7152 * rgb[i + 1] + .0722 * rgb[i + 2]) for i in range(0, len(rgb), 3)]
    return {
        "mean_luma": statistics.fmean(luminance),
        "luma_contrast": statistics.pstdev(luminance),
        "near_black_ratio": sum(value < 12 for value in luminance) / len(luminance),
        "dark_panel_ratio": sum(value < 90 for value in luminance) / len(luminance),
        "bright_foreground_ratio": sum(value > 200 for value in luminance) / len(luminance),
        "saturated_ratio": sum(max(rgb[i:i + 3]) > 170 and max(rgb[i:i + 3]) - min(rgb[i:i + 3]) > 70 for i in range(0, len(rgb), 3)) / len(luminance),
    }


def extract_region(video, seconds, crop, scale):
    return subprocess.check_output([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(seconds), "-i", str(video),
        "-frames:v", "1", "-vf", f"crop={crop},scale={scale}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])


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
        "-frames:v", "1", "-vf", "scale=90:160", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])
    whole = pixel_metrics(ppm)
    panel = pixel_metrics(extract_region(video, seconds, "996:530:42:165", "100:53"))
    headline = pixel_metrics(extract_region(video, seconds, "878:310:112:255", "88:31"))
    accent = pixel_metrics(extract_region(video, seconds, "16:360:70:205", "8:180"))
    hero = pixel_metrics(extract_region(video, seconds, "900:700:90:760", "90:70"))
    headline_not_empty = headline["bright_foreground_ratio"] >= .01
    panel_present = panel["dark_panel_ratio"] >= .25
    headline_contrast = headline["luma_contrast"] >= 22
    accent_present = accent["saturated_ratio"] >= .25
    hero_present = hero["luma_contrast"] >= 8 or hero["mean_luma"] >= 70
    result = {
        "time_seconds": seconds, "file": str(png),
        "mean_luma": round(whole["mean_luma"], 2), "luma_contrast": round(whole["luma_contrast"], 2),
        "near_black_ratio": round(whole["near_black_ratio"], 4),
        "not_black_or_empty": 20 <= whole["mean_luma"] <= 235 and whole["near_black_ratio"] < .75,
        "high_contrast": whole["luma_contrast"] >= 22,
        "headline_area_not_empty": headline_not_empty, "headline_panel_present": panel_present,
        "headline_area_contrast": headline_contrast, "accent_line_present": accent_present,
        "hero_visual_present": hero_present,
        "regions": {name: {key: round(value, 4) for key, value in metrics.items()} for name, metrics in
                    (("panel", panel), ("headline", headline), ("accent", accent), ("hero", hero))},
    }
    frames.append(result)
    checks[f"frame_{label}s_visible"] = result["not_black_or_empty"]
    checks[f"frame_{label}s_contrast"] = result["high_contrast"]
    checks[f"frame_{label}s_headline_area_not_empty"] = headline_not_empty
    checks[f"frame_{label}s_headline_panel_present"] = panel_present
    checks[f"frame_{label}s_headline_area_contrast"] = headline_contrast
    checks[f"frame_{label}s_accent_line_present"] = accent_present
    checks[f"frame_{label}s_hero_visual_present"] = hero_present
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
