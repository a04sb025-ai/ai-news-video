#!/usr/bin/env python3
"""Render a lively, zero-API vertical news short from a story JSON file."""
import json
import shutil
import subprocess
import sys
import tempfile
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
FPS, DURATION = 30, 13
PALETTE = ["18213A", "122E3A", "25304A", "111827"]
ASSET_DIR = Path(__file__).resolve().parents[1] / "assets/generated"
STORY_IMAGES = [
    ASSET_DIR / "scene-teen-hero.png",
    ASSET_DIR / "scene-teen-chat.png",
    ASSET_DIR / "scene-learning-safety.png",
]
USE_STORY_IMAGES = all(image.is_file() and image.stat().st_size > 0 for image in STORY_IMAGES)


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
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    wav = tmp / "voice.wav"
    ass = tmp / "motion.ass"
    narration = tmp / "narration.txt"
    narration.write_text("\n".join(cue["narration"] for cue in story["script"]))
    subprocess.run(
        ["open_jtalk", "-x", str(dictionary), "-m", str(voice), "-r", "1.18", "-ow", str(wav), str(narration)],
        check=True,
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
        if not (USE_STORY_IMAGES and index in (0, 1, 2)):
            events.append(vector(start, end, rect_path(0, 0, WIDTH, HEIGHT), color))
        # Progress rail makes the short structure readable at a glance.
        events.append(vector(start, end, rect_path(72, 1735, 936, 8), "4A526A", layer=1))
        progress = round(936 * end / DURATION)
        events.append(vector(start, end, rect_path(72, 1735, progress, 8), "58D6FF", layer=2))

        if index == 0:
            events.append(dialogue(start, end, "Eyebrow", "AI NEWS  •  13 SEC", r"\fad(100,100)", 3))
            # The opening is a thumbnail: image/subject first, one large conclusion, no decorative hero icon.
            events.append(vector(start, end, rect_path(42, 165, 996, 530), "101528", r"\alpha&H28&\fad(80,80)", 2))
            events.append(vector(start, end, rect_path(70, 205, 16, 360), "58D6FF", r"\fad(80,80)", 3))
            events.append(dialogue(start, end, "Headline", cue["caption"], r"\an7\pos(112,255)\fad(80,80)", 4))
            events.append(dialogue(start, end, "Small", "OpenAIが新しい10代向け体験", r"\an7\pos(115,610)\fs36\bord2\fad(100,80)", 4))
        elif index == 1:
            events.append(dialogue(start, end, "Eyebrow", "つまり、何？", r"\fad(100,100)", 3))
            if not USE_STORY_IMAGES:
                events.append(vector(start, end, rect_path(145, 430, 790, 690), "FFFFFF", r"\fad(120,100)", 2))
                events.append(vector(start + .20, end, rect_path(220, 545, 520, 100), "EAF2FF", r"\fad(100,100)", 3))
                events.append(dialogue(start + .20, end, "Small", "宿題をわかりやすく教えて", r"\pos(480,595)\fad(100,100)", 4))
                events.append(vector(start + .55, end, rect_path(340, 700, 515, 100), "C9F7FF", r"\fad(100,100)", 3))
                events.append(dialogue(start + .55, end, "Small", "もちろん！一緒に考えよう", r"\pos(597,750)\1c&H151B2B&\fad(100,100)", 4))
            events.append(vector(start, end, rect_path(52, 1310, 976, 390), "101528", r"\alpha&H18&\fad(120,100)", 3))
            events.append(dialogue(start, end, "Caption", cue["caption"], r"\fad(120,100)", 4))
        elif index == 2:
            events.append(dialogue(start, end, "Eyebrow", "ここがポイント", r"\fad(100,100)", 3))
            if not USE_STORY_IMAGES:
                events.append(vector(start, end, rect_path(100, 440, 405, 610), "FFF3C4", r"\fad(100,100)", 2))
                events.append(vector(start + .20, end, rect_path(575, 440, 405, 610), "C9F7FF", r"\fad(100,100)", 2))
                # Simple book and shield symbols, drawn without external assets.
                events.append(vector(start, end, "m 190 590 l 300 565 300 800 190 825 m 300 565 l 410 590 410 825 300 800", "F2B84B", r"\fad(100,100)", 3))
                events.append(vector(start + .20, end, "m 775 555 l 900 605 875 785 b 865 850 815 890 775 910 b 735 890 685 850 675 785 l 650 605", "58D6FF", r"\fad(100,100)", 3))
                events.append(dialogue(start, end, "Label", "学 習", r"\pos(300,940)\fs44\fad(100,100)", 4))
                events.append(dialogue(start + .20, end, "Label", "安 全", r"\pos(775,940)\fs44\fad(100,100)", 4))
            events.append(vector(start, end, rect_path(52, 1310, 976, 390), "101528", r"\alpha&H18&\fad(120,100)", 3))
            events.append(dialogue(start, end, "Caption", cue["caption"], r"\fad(120,100)", 4))
        else:
            events.append(vector(start, end, rect_path(190, 760, 700, 8), "58D6FF", r"\fad(120,160)", 2))
            events.append(dialogue(start, end, "Outro", "AIニュース速報", r"\pos(540,900)\fs64\fad(120,160)", 3))
            events.append(dialogue(start, end, "Outro", "AIツールウォッチ", r"\pos(540,1010)\fs52\1c&H58D6FF&\fad(160,160)", 3))

    ass.write_text(header + "\n".join(events) + "\n")
    command = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x111827:s={WIDTH}x{HEIGHT}:r={FPS}:d={DURATION}",
        "-i", str(wav),
    ]
    if USE_STORY_IMAGES:
        for image in STORY_IMAGES:
            command.extend(["-loop", "1", "-i", str(image)])
        filters = (
            f"[2:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},"
            f"zoompan=z='min(zoom+0.00035,1.035)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=90:s={WIDTH}x{HEIGHT}:fps={FPS},fade=t=in:st=0:d=0.12:alpha=1,setpts=PTS[hero];"
            f"[3:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},"
            f"zoompan=z='min(zoom+0.0006,1.05)':x='iw/2-(iw/zoom/2)+10*sin(on/30)':"
            f"y='ih/2-(ih/zoom/2)':d=120:s={WIDTH}x{HEIGHT}:fps={FPS},"
            "fade=t=in:st=0:d=0.2:alpha=1,setpts=PTS+3/TB[teen];"
            f"[4:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},"
            f"zoompan=z='min(zoom+0.0006,1.05)':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)+8*cos(on/35)':d=120:s={WIDTH}x{HEIGHT}:fps={FPS},"
            "fade=t=in:st=0:d=0.2:alpha=1,setpts=PTS+7/TB[safety];"
            "[0:v][hero]overlay=enable='between(t,0,3)'[withhero];"
            "[withhero][teen]overlay=enable='between(t,3,7)'[withteen];"
            "[withteen][safety]overlay=enable='between(t,7,11)',"
            f"subtitles={ass}[video]"
        )
        command.extend(["-filter_complex", filters, "-map", "[video]", "-map", "1:a"])
    else:
        print("Story images unavailable; using motion-graphics fallback", file=sys.stderr)
        command.extend(["-vf", f"subtitles={ass}"])
    command.extend([
        "-af", f"apad=pad_dur={DURATION},loudnorm=I=-16:TP=-1.5:LRA=11", "-t", str(DURATION),
        "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(output),
    ])
    subprocess.run(command, check=True)
print(output)
