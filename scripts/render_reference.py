#!/usr/bin/env python3
"""Render a lively, zero-API vertical news short from a story JSON file."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path


story_path, output = map(Path, sys.argv[1:3])
story = json.loads(story_path.read_text())
for command in ("ffmpeg", "open_jtalk"):
    if not shutil.which(command):
        raise SystemExit(f"Missing command: {command}")

dictionary = next(iter(Path("/var/lib/mecab/dic/open-jtalk").glob("*")), None)
voice = next(iter(Path("/usr/share/hts-voice").rglob("*.htsvoice")), None)
if not dictionary or not voice:
    raise SystemExit("Open JTalk dictionary/voice not found")

WIDTH, HEIGHT = 1080, 1920
FPS = 30
DURATION = story["script"][-1]["end"]
SAFE_OPENING = os.environ.get("OPENING_SAFE_MODE") == "1"
PALETTE = ["18213A", "122E3A", "25304A", "111827"]
ROOT = Path(__file__).resolve().parents[1]
IMAGE_CONFIG = json.loads((ROOT / "config/image-generation.json").read_text())
ASSET_DIR = ROOT / story.get("image_asset_dir", str(Path(IMAGE_CONFIG["output_directory"]) / IMAGE_CONFIG["prompt_version"]))
STORY_IMAGES = [ASSET_DIR / name for name in story.get("image_assets", [
    "scene-teen-hero.png", "scene-teen-thinking.png", "scene-teen-safety.png", "scene-teen-healthy-use.png",
])]
USE_STORY_IMAGES = len(STORY_IMAGES) == 4 and all(image.is_file() and image.stat().st_size > 0 for image in STORY_IMAGES)
IS_DAILY = "content_hash" in story


def stamp(seconds):
    centiseconds = round(seconds * 100)
    return (
        f"{centiseconds // 360000}:"
        f"{centiseconds // 6000 % 60:02}:"
        f"{centiseconds // 100 % 60:02}."
        f"{centiseconds % 100:02}"
    )


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
# Never expose an MP4 whose moov atom is still being written.  QA and uploaders only
# see ``output`` after ffmpeg has closed, verified, and atomically renamed the file.
temporary_output = output.with_name(f".{output.stem}.rendering{output.suffix}")
temporary_output.unlink(missing_ok=True)
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    wav = tmp / "voice.wav"
    ass = tmp / "motion.ass"
    cue_wavs = []
    cue_durations = []
    for index, cue in enumerate(story["script"]):
        narration = tmp / f"narration-{index}.txt"
        raw_wav = tmp / f"voice-{index}-raw.wav"
        fitted_wav = tmp / f"voice-{index}.wav"
        narration.write_text(cue["narration"])
        subprocess.run(
            ["open_jtalk", "-x", str(dictionary), "-m", str(voice), "-r", "1.18", "-ow", str(raw_wav), str(narration)],
            check=True,
        )
        with wave.open(str(raw_wav)) as audio:
            raw_duration = audio.getnframes() / audio.getframerate()
        slot = cue["end"] - cue["start"]
        speed = max(1.0, raw_duration / max(slot - .12, .5))
        filters = []
        while speed > 2:
            filters.append("atempo=2")
            speed /= 2
        filters.append(f"atempo={speed:.4f}")
        filters.extend((f"apad=pad_dur={slot}", f"atrim=duration={slot}"))
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_wav),
             "-af", ",".join(filters), str(fitted_wav)], check=True,
        )
        cue_wavs.append(fitted_wav)
        cue_durations.append(slot)
    audio_inputs = [value for cue_wav in cue_wavs for value in ("-i", str(cue_wav))]
    audio_filter = "".join(f"[{i}:a]apad,atrim=duration={duration}[a{i}];" for i, duration in enumerate(cue_durations))
    audio_filter += "".join(f"[a{i}]" for i in range(len(cue_wavs))) + f"concat=n={len(cue_wavs)}:v=0:a=1[out]"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *audio_inputs,
         "-filter_complex", audio_filter, "-map", "[out]", str(wav)], check=True,
    )

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Eyebrow,Noto Sans CJK JP,38,&H00C9F7FF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,4,0,1,0,0,8,90,90,132,1
Style: Headline,Noto Sans CJK JP,112,&H00FFFFFF,&H00FFFFFF,&H00101528,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,8,90,90,270,1
Style: Caption,Noto Sans CJK JP,72,&H00FFFFFF,&H00FFFFFF,&H00101528,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,2,95,95,280,1
Style: Label,Noto Sans CJK JP,42,&H00151B2B,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,0,0,5,20,20,20,1
Style: Small,Noto Sans CJK JP,33,&H00D5DDF2,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,0,0,5,20,20,20,1
Style: Outro,Noto Sans CJK JP,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,0,0,5,60,60,60,1
Style: Shape,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events = []
    for index, cue in enumerate(story["script"]):
        start, end = cue["start"], cue["end"]
        color = PALETTE[index % len(PALETTE)]
        if not (USE_STORY_IMAGES and index < len(STORY_IMAGES)):
            events.append(vector(start, end, rect_path(0, 0, WIDTH, HEIGHT), color))
        # Progress rail makes the short structure readable at a glance.
        events.append(vector(start, end, rect_path(72, 1735, 936, 8), "4A526A", layer=1))
        progress = round(936 * end / DURATION)
        events.append(vector(start, end, rect_path(72, 1735, progress, 8), "58D6FF", layer=2))

        if index == 0:
            if IS_DAILY and not USE_STORY_IMAGES and SAFE_OPENING:
                # A deterministic high-contrast editorial field for image-free QA;
                # it carries no facts or topic-specific iconography.
                events.append(vector(start, end, rect_path(0, 720, WIDTH, 820), "E8EDF7", layer=1))
                events.append(vector(start, end, rect_path(0, 1540, WIDTH, 195), "25304A", layer=1))
            events.append(dialogue(start, end, "Eyebrow", cue.get("label", "AI NEWS"), layer=3))
            # The opening is a thumbnail: image/subject first, one large conclusion, no decorative hero icon.
            panel_alpha = "&H08&" if SAFE_OPENING else "&H28&"
            # Opening frames double as thumbnails. Keep every major element fully
            # opaque from frame zero through the final opening frame (2.967s).
            events.append(vector(start, end, rect_path(42, 165, 996, 530), "101528", rf"\alpha{panel_alpha}", 2))
            events.append(vector(start, end, rect_path(70, 205, 16, 360), "58D6FF", layer=3))
            events.append(dialogue(start, end, "Headline", cue["caption"], r"\an7\pos(112,255)", 4))
            events.append(dialogue(start, end, "Small", cue.get("subcaption", ""), r"\an7\pos(115,610)\fs34\bord2", 4))
        elif index == 1:
            events.append(dialogue(start, end, "Eyebrow", cue.get("label", "つまり、何？"), r"\fad(100,100)", 3))
            if not USE_STORY_IMAGES:
                if IS_DAILY:
                    events.append(vector(start, end, rect_path(130, 430, 820, 620), "25304A", r"\fad(120,100)", 2))
                    events.append(vector(start + .2, end, rect_path(190, 510, 700, 18), "58D6FF", r"\fad(100,100)", 3))
                    events.append(vector(start + .4, end, rect_path(190, 590, 520, 18), "C9F7FF", r"\fad(100,100)", 3))
                else:
                    events.append(vector(start, end, rect_path(145, 430, 790, 690), "FFFFFF", r"\fad(120,100)", 2))
                    events.append(vector(start + .20, end, rect_path(220, 545, 520, 100), "EAF2FF", r"\fad(100,100)", 3))
                    events.append(dialogue(start + .20, end, "Small", "宿題をわかりやすく教えて", r"\pos(480,595)\fad(100,100)", 4))
                    events.append(vector(start + .55, end, rect_path(340, 700, 515, 100), "C9F7FF", r"\fad(100,100)", 3))
                    events.append(dialogue(start + .55, end, "Small", "もちろん！一緒に考えよう", r"\pos(597,750)\1c&H151B2B&\fad(100,100)", 4))
            events.append(vector(start, end, rect_path(52, 1310, 976, 390), "101528", r"\alpha&H18&\fad(120,100)", 3))
            events.append(dialogue(start, end, "Caption", cue["caption"], r"\fad(120,100)", 4))
        elif index == 2:
            events.append(dialogue(start, end, "Eyebrow", cue.get("label", "ここがポイント"), r"\fad(100,100)", 3))
            if not USE_STORY_IMAGES and IS_DAILY:
                events.append(vector(start, end, rect_path(110, 450, 860, 590), "25304A", r"\fad(100,100)", 2))
                events.append(vector(start + .2, end, rect_path(170, 520, 24, 430), "58D6FF", r"\fad(100,100)", 3))
            elif not USE_STORY_IMAGES:
                events.append(vector(start, end, rect_path(100, 440, 405, 610), "FFF3C4", r"\fad(100,100)", 2))
                events.append(vector(start + .20, end, rect_path(575, 440, 405, 610), "C9F7FF", r"\fad(100,100)", 2))
                # Simple book and shield symbols, drawn without external assets.
                events.append(vector(start, end, "m 190 590 l 300 565 300 800 190 825 m 300 565 l 410 590 410 825 300 800", "F2B84B", r"\fad(100,100)", 3))
                events.append(vector(start + .20, end, "m 775 555 l 900 605 875 785 b 865 850 815 890 775 910 b 735 890 685 850 675 785 l 650 605", "58D6FF", r"\fad(100,100)", 3))
                events.append(dialogue(start, end, "Label", "学 習", r"\pos(300,940)\fs44\fad(100,100)", 4))
                events.append(dialogue(start + .20, end, "Label", "安 全", r"\pos(775,940)\fs44\fad(100,100)", 4))
            events.append(vector(start, end, rect_path(52, 1310, 976, 390), "101528", r"\alpha&H18&\fad(120,100)", 3))
            events.append(dialogue(start, end, "Caption", cue["caption"], r"\fad(120,100)", 4))
        elif index < len(story["script"]) - 1:
            events.append(dialogue(start, end, "Eyebrow", cue.get("label", "さらに"), r"\fad(100,100)", 3))
            if not USE_STORY_IMAGES and IS_DAILY:
                events.append(vector(start, end, rect_path(145, 470, 790, 610), "25304A", r"\fad(120,100)", 2))
                events.append(vector(start + .2, end, rect_path(215, 570, 650, 22), "58D6FF", r"\fad(100,100)", 3))
            elif not USE_STORY_IMAGES:
                events.append(vector(start, end, rect_path(145, 470, 790, 610), "C9F7FF", r"\fad(120,100)", 2))
                events.append(dialogue(start, end, "Label", "休 憩", r"\pos(540,760)\fs72\fad(100,100)", 4))
            events.append(vector(start, end, rect_path(52, 1310, 976, 390), "101528", r"\alpha&H18&\fad(120,100)", 3))
            events.append(dialogue(start, end, "Caption", cue["caption"], r"\fad(120,100)", 4))
        else:
            events.append(vector(start, end, rect_path(190, 760, 700, 8), "58D6FF", r"\fad(120,160)", 2))
            events.append(dialogue(start, end, "Outro", "AIニュース速報", r"\pos(540,900)\fs64\fad(120,160)", 3))
            events.append(dialogue(start, end, "Outro", "AIツールウォッチ", r"\pos(540,1010)\fs52\1c&H58D6FF&\fad(160,160)", 3))

    ass.write_text(header + "\n".join(events) + "\n")
    command = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x18213A:s={WIDTH}x{HEIGHT}:r={FPS}:d={DURATION}",
        "-i", str(wav),
    ]
    if USE_STORY_IMAGES:
        for image in STORY_IMAGES:
            command.extend(["-loop", "1", "-i", str(image)])
        scene_streams = []
        for offset, (start, end) in enumerate(((0, 3), (3, 6), (6, 9), (9, 12)), start=2):
            duration_frames = round((end - start) * FPS)
            zoom = "0.00035" if start == 0 else "0.0006"
            fade = "" if start == 0 else "fade=t=in:st=0:d=0.12:alpha=1,"
            scene_streams.append(
                f"[{offset}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},"
                f"zoompan=z='min(zoom+{zoom},1.05)':x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':d={duration_frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
                f"{fade}setpts=PTS+{start}/TB[scene{offset}];"
            )
        overlays = (
            "[0:v][scene2]overlay=enable='between(t,0,3)'[v2];"
            "[v2][scene3]overlay=enable='between(t,3,6)'[v3];"
            "[v3][scene4]overlay=enable='between(t,6,9)'[v4];"
            "[v4][scene5]overlay=enable='between(t,9,12)',"
            f"subtitles={ass}[video]"
        )
        filters = "".join(scene_streams) + overlays
        command.extend(["-filter_complex", filters, "-map", "[video]", "-map", "1:a"])
    else:
        print("Story images unavailable; using motion-graphics fallback", file=sys.stderr)
        command.extend(["-vf", f"subtitles={ass}"])
    command.extend([
        "-af", f"apad=pad_dur={DURATION},loudnorm=I=-16:TP=-1.5:LRA=11", "-t", str(DURATION),
        "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(temporary_output),
    ])
    try:
        subprocess.run(command, check=True)
        # A complete decode before publication catches truncated tails and invalid
        # packets while the temporary file can still be safely discarded.
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(temporary_output), "-map", "0", "-f", "null", "-"],
            check=True,
        )
        temporary_output.replace(output)
    finally:
        temporary_output.unlink(missing_ok=True)
manifest = {"content_hash": story.get("content_hash"), "used_generated_images": USE_STORY_IMAGES,
            "image_directory": str(ASSET_DIR),
            "images": [str(image) for image in STORY_IMAGES] if USE_STORY_IMAGES else []}
output.with_suffix(".render.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(output)
