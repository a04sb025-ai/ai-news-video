#!/usr/bin/env python3
"""Render the four-page explanatory daily AI-news format with full narration subtitles."""
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
if story.get("explanation_contract") != "four-page-v1":
    raise SystemExit("render_explainer.py requires explanation_contract=four-page-v1")
for command in ("ffmpeg", "open_jtalk"):
    if not shutil.which(command):
        raise SystemExit(f"Missing command: {command}")

dictionary = next(iter(Path("/var/lib/mecab/dic/open-jtalk").glob("*")), None)
voice = next(iter(Path("/usr/share/hts-voice").rglob("*.htsvoice")), None)
if not dictionary or not voice:
    raise SystemExit("Open JTalk dictionary/voice not found")

WIDTH, HEIGHT, FPS = 1080, 1920, 30
DURATION = story["script"][-1]["end"]
ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / story["image_asset_dir"]
STORY_IMAGES = [ASSET_DIR / name for name in story["image_assets"]]
USE_STORY_IMAGES = len(STORY_IMAGES) == 4 and all(path.is_file() and path.stat().st_size > 0 for path in STORY_IMAGES)
MOZO_OPENING_ASSET = ROOT / story["opening"]["character_asset"]
USE_MOZO_OPENING_ASSET = MOZO_OPENING_ASSET.is_file() and MOZO_OPENING_ASSET.stat().st_size > 64 and MOZO_OPENING_ASSET.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


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


output.parent.mkdir(parents=True, exist_ok=True)
temporary_output = output.with_name(f".{output.stem}.rendering{output.suffix}")
temporary_output.unlink(missing_ok=True)
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    wav = tmp / "voice.wav"
    ass = tmp / "explainer.ass"
    cue_wavs, cue_durations = [], []
    for index, cue in enumerate(story["script"]):
        narration = tmp / f"narration-{index}.txt"
        raw_wav = tmp / f"voice-{index}-raw.wav"
        fitted_wav = tmp / f"voice-{index}.wav"
        narration.write_text(cue["narration"])
        subprocess.run(["open_jtalk", "-x", str(dictionary), "-m", str(voice), "-r", "1.12", "-ow", str(raw_wav), str(narration)], check=True)
        with wave.open(str(raw_wav)) as audio:
            raw_duration = audio.getnframes() / audio.getframerate()
        slot = cue["end"] - cue["start"]
        speed = max(1.0, raw_duration / max(slot - .16, .6))
        filters = []
        while speed > 2:
            filters.append("atempo=2")
            speed /= 2
        filters.append(f"atempo={speed:.4f}")
        filters.extend((f"apad=pad_dur={slot}", f"atrim=duration={slot}"))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_wav), "-af", ",".join(filters), str(fitted_wav)], check=True)
        cue_wavs.append(fitted_wav)
        cue_durations.append(slot)

    audio_inputs = [value for cue_wav in cue_wavs for value in ("-i", str(cue_wav))]
    audio_filter = "".join(f"[{i}:a]apad,atrim=duration={duration}[a{i}];" for i, duration in enumerate(cue_durations))
    audio_filter += "".join(f"[a{i}]" for i in range(len(cue_wavs))) + f"concat=n={len(cue_wavs)}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *audio_inputs,
                    "-filter_complex", audio_filter, "-map", "[out]", str(wav)], check=True)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Eyebrow,Noto Sans CJK JP,38,&H00FFF1C7,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,4,0,1,0,0,8,70,70,105,1
Style: OpeningHeadline,Noto Sans CJK JP,106,&H00FFFFFF,&H00FFFFFF,&H00009BFF,&H00101528,-1,0,0,0,100,100,0,0,1,8,3,7,90,90,210,1
Style: OpeningSupport,Noto Sans CJK JP,52,&H00151B2B,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,90,90,0,1
Style: SectionHeadline,Noto Sans CJK JP,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,90,90,0,1
Style: Support,Noto Sans CJK JP,40,&H00FFF1C7,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,90,90,0,1
Style: Subtitle,Noto Sans CJK JP,36,&H00FFFFFF,&H00FFFFFF,&H00101528,&H00101528,-1,0,0,0,100,100,0,0,3,2,0,7,100,100,0,1
Style: OpeningSubtitle,Noto Sans CJK JP,31,&H00FFFFFF,&H00FFFFFF,&H00101528,&H00101528,-1,0,0,0,100,100,0,0,3,2,0,5,25,25,0,1
Style: Bubble,Noto Sans CJK JP,42,&H00151B2B,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,20,20,20,1
Style: Outro,Noto Sans CJK JP,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,0,0,5,60,60,60,1
Style: Shape,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events = []
    page_cues = story["script"][:4]
    for index, cue in enumerate(story["script"]):
        start, end = cue["start"], cue["end"]
        events.append(vector(start, end, rect_path(72, 1760, 936, 8), "4A526A", layer=1))
        progress = round(936 * end / DURATION)
        events.append(vector(start, end, rect_path(72, 1760, progress, 8), "58D6FF", layer=2))

        if index == 0:
            events.append(vector(start, end, rect_path(42, 140, 996, 520), "101528", r"\alpha&H20&", 3))
            events.append(vector(start, end, rect_path(70, 190, 16, 350), "00A5FF", layer=4))
            events.append(dialogue(start, end, "Eyebrow", cue["label"], layer=5))
            events.append(dialogue(start, end, "OpeningHeadline", cue["caption"], r"\pos(112,225)", 6))
            events.append(vector(start, end, rect_path(82, 710, 916, 430), "F3EFE8", r"\alpha&H06&", 4))
            events.append(dialogue(start, end, "OpeningSupport", cue["support_text"], r"\pos(540,925)\fs52", 6))
            events.append(vector(start, end, "m 405 1350 b 405 1310 445 1290 500 1298 l 885 1298 b 940 1302 965 1335 958 1380 l 950 1430 b 940 1475 900 1495 845 1488 l 530 1488 b 475 1490 430 1465 425 1425 l 370 1470 395 1405 b 390 1385 395 1365 405 1350", "FFF4D6", layer=6))
            events.append(dialogue(start, end, "Bubble", cue.get("mozo_line", "ここがポイント"), r"\pos(680,1393)", 7))
            events.append(vector(start, end, rect_path(390, 1530, 630, 180), "101528", r"\alpha&H14&", 6))
            events.append(dialogue(start, end, "OpeningSubtitle", cue["subtitle"], r"\pos(705,1620)", 8))
        elif index < 4:
            events.append(dialogue(start, end, "Eyebrow", cue["label"], r"\fad(100,100)", 4))
            events.append(vector(start, end, rect_path(42, 1180, 996, 550), "101528", r"\alpha&H16&\fad(100,100)", 4))
            events.append(dialogue(start, end, "SectionHeadline", cue["caption"], r"\pos(90,1240)\fad(100,100)", 6))
            events.append(dialogue(start, end, "Support", cue["support_text"], r"\pos(90,1395)\fad(100,100)", 6))
            events.append(dialogue(start, end, "Subtitle", cue["subtitle"], r"\pos(90,1510)\fad(100,100)", 7))
        else:
            events.append(vector(start, end, rect_path(190, 760, 700, 8), "58D6FF", r"\fad(100,120)", 2))
            events.append(dialogue(start, end, "Outro", "今日のAIニュース", r"\pos(540,880)\fs58\fad(100,120)", 3))
            events.append(dialogue(start, end, "Outro", "AIツールウォッチ", r"\pos(540,1000)\fs50\1c&H58D6FF&\fad(100,120)", 3))

    ass.write_text(header + "\n".join(events) + "\n")

    command = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x18213A:s={WIDTH}x{HEIGHT}:r={FPS}:d={DURATION}", "-i", str(wav)]
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
            filters.append(f"[{image_index}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},setsar=1[{scaled}];")
            filters.append(f"{current}[{scaled}]overlay=enable='between(t,{cue['start']},{cue['end']})'[{out}];")
            current = f"[{out}]"
    if USE_MOZO_OPENING_ASSET:
        filters.append(f"[{mozo_index}:v]scale=350:-1[mozo];")
        filters.append(f"{current}[mozo]overlay=55:1340:enable='between(t,0,{page_cues[0]['end']})'[withmozo];")
        current = "[withmozo]"
    filters.append(f"{current}subtitles={ass}[video]")
    command.extend(["-filter_complex", "".join(filters), "-map", "[video]", "-map", "1:a"])
    command.extend(["-af", f"apad=pad_dur={DURATION},loudnorm=I=-16:TP=-1.5:LRA=11", "-t", str(DURATION),
                    "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", str(temporary_output)])
    try:
        subprocess.run(command, check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(temporary_output), "-map", "0", "-f", "null", "-"], check=True)
        temporary_output.replace(output)
    finally:
        temporary_output.unlink(missing_ok=True)

manifest = {
    "content_hash": story.get("content_hash"),
    "used_generated_images": USE_STORY_IMAGES,
    "used_mozo_opening_asset": USE_MOZO_OPENING_ASSET,
    "mozo_opening_asset": str(MOZO_OPENING_ASSET) if USE_MOZO_OPENING_ASSET else None,
    "mozo_opening_asset_sha256": hashlib.sha256(MOZO_OPENING_ASSET.read_bytes()).hexdigest() if USE_MOZO_OPENING_ASSET else None,
    "image_directory": str(ASSET_DIR),
    "images": [str(image) for image in STORY_IMAGES] if USE_STORY_IMAGES else [],
    "renderer": "four-page-explainer-v1",
    "full_narration_subtitles": True,
}
output.with_suffix(".render.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(output)
