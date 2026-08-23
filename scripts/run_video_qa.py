#!/usr/bin/env python3
"""Run explainable decode and black-frame QA and retain all evidence."""
import json
import re
import subprocess
import sys
from pathlib import Path

video, report_dir = Path(sys.argv[1]), Path(sys.argv[2])
report_dir.mkdir(parents=True, exist_ok=True)


def run(command):
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


decode = run(["ffmpeg", "-hide_banner", "-v", "warning", "-xerror", "-i", str(video), "-map", "0", "-f", "null", "-"])
decode_log = decode.stderr
(report_dir / "decode-errors.txt").write_text(decode_log)
decode_ok = decode.returncode == 0 and not re.search(
    r"corrupt|invalid (?:data|packet)|decode error|non.monoton|moov atom|error while decoding|timestamp discontinu", decode_log, re.I
)

black = run([
    "ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
    "-vf", "blackdetect=d=0.10:pix_th=0.10", "-an", "-f", "null", "-",
])
(report_dir / "blackdetect.txt").write_text(black.stderr)
events = []
pattern = re.compile(r"black_start:(?P<start>[\d.]+)\s+black_end:(?P<end>[\d.]+)\s+black_duration:(?P<duration>[\d.]+)")
for index, match in enumerate(pattern.finditer(black.stderr)):
    item = {key: float(value) for key, value in match.groupdict().items()}
    item.update(frame_number=round(item["start"] * 30), black_pixel_ratio=">= 0.98")
    timestamp = min(item["start"] + item["duration"] / 2, item["end"])
    png = report_dir / f"black-frame-{index:02}.png"
    shot = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(timestamp), "-i", str(video), "-frames:v", "1", str(png)])
    item["artifact"] = str(png) if shot.returncode == 0 else None
    events.append(item)
black_ok = black.returncode == 0 and not events

results = {
    "decode_error_free": {
        "passed": bool(decode_ok),
        "reason": "complete ffmpeg decode succeeded without corruption, packet, codec, or timestamp errors" if decode_ok else "ffmpeg detected a decode/container/packet/timestamp error",
        "details": {"exit_code": decode.returncode, "log": str(report_dir / "decode-errors.txt"), "diagnostic": decode_log.strip() or "none"},
    },
    "black_frame_check": {
        "passed": bool(black_ok),
        "reason": "no unintended black interval of 0.10s or longer was detected" if black_ok else f"{len(events)} black interval(s) detected",
        "details": {"exit_code": black.returncode, "events": events, "log": str(report_dir / "blackdetect.txt")},
    },
}
(report_dir / "video-qa.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
lines = []
for name, result in results.items():
    lines.extend((f"QA: {name}", f"RESULT: {'PASS' if result['passed'] else 'FAIL'}", f"REASON: {result['reason']}", f"DETAIL: {json.dumps(result['details'], ensure_ascii=False)}", ""))
(report_dir / "video-qa.txt").write_text("\n".join(lines))
print("\n".join(lines))
raise SystemExit(0 if all(result["passed"] for result in results.values()) else 1)
