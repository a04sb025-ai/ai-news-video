#!/usr/bin/env python3
"""Render adaptive daily AI-news explainers with mobile-first thumbnail openings."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

story_path, output = map(Path, sys.argv[1:3])
story = json.loads(story_path.read_text())
if story.get("explanation_contract") != "adaptive-pages-v1":
    raise SystemExit("render_adaptive_explainer.py requires explanation_contract=adaptive-pages-v1")
for command in ("ffmpeg", "open_jtalk"):
    if not shutil.which(command):
        raise SystemExit(f"Missing command: {command}")

dictionary = next(iter(Path("/var/lib/mecab/dic/open-jtalk").glob("*")), None)
voice = next(iter(Path("/usr/share/hts-voice").rglob("*.htsvoice")), None)
if not dictionary or not voice:
    raise SystemExit("Open JTalk dictionary/voice not found")

WIDTH, HEIGHT, FPS = 1080, 1920, 30
DURATION = float(story["script"][-1]["end"])
ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / story["image_asset_dir"]
STORY_IMAGES = [ASSET_DIR / name for name in story.get("image_assets", [])]
USE_STORY_IMAGES = bool(STORY_IMAGES) and all(path.is_file() and path.stat().st_size > 0 for path in STORY_IMAGES)
MOZO_OPENING_ASSET = ROOT / story["opening"]["character_asset"]
USE_MOZO_OPENING_ASSET = (
    MOZO_OPENING_ASSET.is_file()
    and MOZO_OPENING_ASSET.stat().st_size > 64
    and MOZO_OPENING_ASSET.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
)
OPENING_STYLE = story.get("opening", {}).get("thumbnail_style", "B")
if OPENING_STYLE not in {"A", "B", "C"}:
    raise SystemExit("opening.thumbnail_style must be A, B or C")
OPENING_END = min(3.0, float(story["script"][0]["end"]))
OPENING_LAYOUT_CONTRACT = "split-text-visual-v1"
BODY_LAYOUT_CONTRACT = "split-text-visual-v1"


def stamp(seconds):
    centiseconds = round(seconds * 100)
    return f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:{centiseconds // 100 % 60:02}.{centiseconds % 100:02}"


def ass_text(value):
    return str(value).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def dialogue(start, end, style, text, override="", layer=0):
    return f"Dialogue: {layer},{stamp(start)},{stamp(end)},{style},,0,0,0,,{{{override}}}{ass_text(text)}"


def vector(start, end, path, color, override="", layer=0):
    tags = rf"\an7\pos(0,0)\1c&H{color}&\bord0\shad0\p1{override}"
    return dialogue(start, end, "Shape", path, tags, layer)


def rect_path(x, y, width, height):
    return f"m {x} {y} l {x + width} {y} {x + width} {y + height} {x} {y + height}"


def add_body_page(events, cue, start, end, *, fade=True):
    """Use the generated scene's reserved lower negative space instead of masking the artwork."""
    if end <= start:
        return
    fade_tag = r"\fad(100,100)" if fade else ""
    events.append(vector(start, end, rect_path(90, 1088, 180, 8), "58D6FF", fade_tag, 4))
    events.append(dialogue(start, end, "Eyebrow", cue["label"], rf"\pos(90,1105){fade_tag}", 5))
    events.append(dialogue(start, end, "SectionHeadline", cue["caption"], rf"\pos(90,1170){fade_tag}", 6))
    events.append(dialogue(start, end, "Support", cue["support_text"], rf"\pos(90,1360){fade_tag}", 6))
    events.append(dialogue(start, end, "Subtitle", cue["subtitle"], rf"\pos(90,1480){fade_tag}", 7))


def add_opening(events, cue):
    """Place typography in the generated image's reserved negative space without masking the artwork."""
    start, end = 0.0, OPENING_END
    if OPENING_STYLE == "A":
        events.append(vector(start, end, rect_path(62, 170, 18, 455), "00A5FF", layer=4))
        events.append(vector(start, end, rect_path(82, 665, 900, 10), "00A5FF", layer=4))
        events.append(dialogue(start, end, "Eyebrow", "AI NEWS", r"\pos(92,155)\1c&H00A5FF&", 5))
        events.append(dialogue(start, end, "OpeningHeadline", cue["caption"], r"\pos(110,235)\fs108\bord10\3c&H08111F&", 7))
        events.append(dialogue(start, end, "OpeningBrand", "AIツールウォッチ", r"\pos(92,620)", 8))
    elif OPENING_STYLE == "C":
        events.append(vector(start, end, rect_path(88, 205, 185, 8), "C87CFF", layer=4))
        events.append(dialogue(start, end, "Eyebrow", "AI NEWS", r"\pos(90,150)\1c&HC87CFF&", 5))
        events.append(dialogue(start, end, "OpeningHeadline", cue["caption"], r"\pos(90,265)\fs120\bord9\3c&H101528&", 7))
        events.append(dialogue(start, end, "OpeningBrand", "AIツールウォッチ", r"\pos(90,650)", 8))
    else:
        events.append(vector(start, end, rect_path(78, 188, 250, 8), "00A5FF", layer=4))
        events.append(vector(start, end, rect_path(338, 188, 112, 8), "C87CFF", layer=4))
        events.append(dialogue(start, end, "Eyebrow", "AI NEWS", r"\pos(86,145)", 5))
        events.append(dialogue(start, end, "OpeningHeadline", cue["caption"], r"\pos(88,255)\fs106\bord9\3c&H101528&", 7))
        events.append(dialogue(start, end, "OpeningBrand", "AIツールウォッチ", r"\pos(88,630)", 8))


output.parent.mkdir(parents=True, exist_ok=True)
temporary_output = output.with_name(f".{output.stem}.rendering{output.suffix}")
temporary_output.unlink(missing_ok=True)

with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    wav = tmp / "voice.wav"
    ass = tmp / "adaptive-explainer.ass"
    cue_wavs, cue_durations = [], []

    for index, cue in enumerate(story["script"]):
        narration = tmp / f"narration-{index}.txt"
        raw_wav = tmp / f"voice-{index}-raw.wav"
        fitted_wav = tmp / f"voice-{index}.wav"
        narration.write_text(cue["narration"])
        subprocess.run([
            "open_jtalk", "-x", str(dictionary), "-m", str(voice), "-r", "1.06",
            "-ow", str(raw_wav), str(narration),
        ], check=True)
        with wave.open(str(raw_wav)) as audio:
            raw_duration = audio.getnframes() / audio.getframerate()
        slot = float(cue["end"]) - float(cue["start"])
        speed = max(1.0, raw_duration / max(slot - .28, .8))
        if speed > 1.32:
            raise SystemExit(
                f"Narration for scene {index + 1} would require {speed:.2f}x speech; "
                "increase scene duration or split the explanation instead of rushing it"
            )
        filters = [f"atempo={speed:.4f}", f"apad=pad_dur={slot}", f"atrim=duration={slot}"]
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_wav),
            "-af", ",".join(filters), str(fitted_wav),
        ], check=True)
        cue_wavs.append(fitted_wav)
        cue_durations.append(slot)

    audio_inputs = [value for cue_wav in cue_wavs for value in ("-i", str(cue_wav))]
    audio_filter = "".join(
        f"[{i}:a]apad,atrim=duration={duration}[a{i}];" for i, duration in enumerate(cue_durations)
    )
    audio_filter += "".join(f"[a{i}]" for i in range(len(cue_wavs))) + f"concat=n={len(cue_wavs)}:v=0:a=1[out]"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *audio_inputs,
        "-filter_complex", audio_filter, "-map", "[out]", str(wav),
    ], check=True)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Eyebrow,Noto Sans CJK JP,40,&H00FFF1C7,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,4,0,1,0,0,7,70,70,105,1
Style: OpeningHeadline,Noto Sans CJK JP,106,&H00FFFFFF,&H00FFFFFF,&H00009BFF,&H00101528,-1,0,0,0,100,100,0,0,1,8,3,7,90,90,210,1
Style: OpeningBrand,Noto Sans CJK JP,34,&H00FFFFFF,&H00FFFFFF,&H00101528,&H00101528,-1,0,0,0,100,100,2,0,1,3,0,7,70,70,0,1
Style: OpeningSubtitle,Noto Sans CJK JP,46,&H00FFFFFF,&H00FFFFFF,&H00101528,&H00101528,-1,0,0,0,100,100,0,0,3,2,0,7,30,30,0,1
Style: SectionHeadline,Noto Sans CJK JP,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,90,90,0,1
Style: Support,Noto Sans CJK JP,48,&H00FFF1C7,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,90,90,0,1
Style: Subtitle,Noto Sans CJK JP,52,&H00FFFFFF,&H00FFFFFF,&H00101528,&H00101528,-1,0,0,0,100,100,0,0,3,2,0,7,90,90,0,1
Style: Outro,Noto Sans CJK JP,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,0,0,5,60,60,60,1
Style: Shape,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

    events = []
    page_cues = story["script"][:-1]
    for index, cue in enumerate(story["script"]):
        start, end = float(cue["start"]), float(cue["end"])
        events.append(vector(start, end, rect_path(72, 1760, 936, 8), "4A526A", layer=1))
        progress = round(936 * end / DURATION)
        events.append(vector(start, end, rect_path(72, 1760, progress, 8), "58D6FF", layer=2))

        if index == 0:
            add_opening(events, cue)
            add_body_page(events, cue, OPENING_END, end, fade=False)
        elif index < len(page_cues):
            add_body_page(events, cue, start, end)
        else:
            events.append(vector(start, end, rect_path(190, 760, 700, 8), "58D6FF", r"\fad(100,120)", 2))
            events.append(dialogue(start, end, "Outro", "今日のAIニュース", r"\pos(540,880)\fs58\fad(100,120)", 3))
            events.append(dialogue(start, end, "Outro", "AIツールウォッチ", r"\pos(540,1000)\fs50\1c&H58D6FF&\fad(100,120)", 3))

    ass.write_text(header + "\n".join(events) + "\n")

    command = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x18213A:s={WIDTH}x{HEIGHT}:r={FPS}:d={DURATION}",
        "-i", str(wav),
    ]
    input_index = 2
    mozo_index = None
    if USE_MOZO_OPENING_ASSET:
        mozo_index = input_index
        command.extend(["-loop", "1", "-framerate", str(FPS), "-i", str(MOZO_OPENING_ASSET)])
        input_index += 1
    image_indices = []
    if USE_STORY_IMAGES:
        for image in STORY_IMAGES:
            image_indices.append(input_index)
            command.extend(["-loop", "1", "-framerate", str(FPS), "-i", str(image)])
            input_index += 1

    filters = []
    current = "[0:v]"
    if USE_STORY_IMAGES:
        for scene_no, (image_index, cue) in enumerate(zip(image_indices, page_cues)):
            scaled = f"scene{scene_no}"
            out = f"v{scene_no + 1}"
            filters.append(
                f"[{image_index}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},setsar=1[{scaled}];"
            )
            filters.append(f"{current}[{scaled}]overlay=enable='between(t,{cue['start']},{cue['end']})'[{out}];")
            current = f"[{out}]"
    if USE_MOZO_OPENING_ASSET:
        filters.append(f"[{mozo_index}:v]scale=190:-1[mozo];")
        filters.append(f"{current}[mozo]overlay=72:1480:enable='between(t,0,{page_cues[0]['end']})'[withmozo];")
        current = "[withmozo]"
    filters.append(f"{current}subtitles={ass}[video]")

    command.extend(["-filter_complex", "".join(filters), "-map", "[video]", "-map", "1:a"])
    command.extend([
        "-af", f"apad=pad_dur={DURATION},loudnorm=I=-16:TP=-1.5:LRA=11", "-t", str(DURATION),
        "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(temporary_output),
    ])
    try:
        subprocess.run(command, check=True)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(temporary_output),
            "-map", "0", "-f", "null", "-",
        ], check=True)
        temporary_output.replace(output)
    finally:
        temporary_output.unlink(missing_ok=True)

manifest = {
    "renderer": "adaptive-explainer-v2-thumbnail-abc",
    "content_hash": story.get("content_hash"),
    "page_count": len(story.get("script", [])) - 1,
    "duration_seconds": DURATION,
    "full_narration_subtitles": True,
    "subtitle_font_size_px": 52,
    "opening_subtitle_font_size_px": 46,
    "opening_headline_font_size_px": {"A": 108, "B": 106, "C": 120}[OPENING_STYLE],
    "opening_headline_target_chars_per_line": 9,
    "opening_thumbnail_style": OPENING_STYLE,
    "opening_support_copy_visible": False,
    "opening_subtitle_visible": False,
    "opening_single_dominant_visual": True,
    "opening_thumbnail_window_seconds": OPENING_END,
    "opening_layout_contract": OPENING_LAYOUT_CONTRACT,
    "opening_text_safe_area_ratio": {"top": 0.0, "bottom": 0.40},
    "opening_dominant_visual_area_ratio": {"top": 0.42, "bottom": 0.82},
    "opening_large_overlay_panel": False,
    "opening_generated_image_full_frame": True,
    "body_layout_contract": BODY_LAYOUT_CONTRACT,
    "body_text_safe_area_ratio": {"top": 0.58, "bottom": 0.91},
    "body_dominant_visual_area_ratio": {"top": 0.08, "bottom": 0.54},
    "body_large_overlay_panel": False,
    "body_generated_image_full_frame": True,
    "used_generated_images": USE_STORY_IMAGES,
    "used_mozo_opening_asset": USE_MOZO_OPENING_ASSET,
    "mozo_opening_asset": str(MOZO_OPENING_ASSET) if USE_MOZO_OPENING_ASSET else None,
    "mozo_opening_asset_sha256": hashlib.sha256(MOZO_OPENING_ASSET.read_bytes()).hexdigest() if USE_MOZO_OPENING_ASSET else None,
    "image_directory": str(ASSET_DIR),
    "images": [str(path) for path in STORY_IMAGES] if USE_STORY_IMAGES else [],
}
output.with_suffix(".render.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")