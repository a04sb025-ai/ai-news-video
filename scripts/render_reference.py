#!/usr/bin/env python3
"""Zero-API reference renderer used to prove the CI media pipeline."""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

story_path, output = map(Path, sys.argv[1:3])
story = json.loads(story_path.read_text())
for command in ("ffmpeg", "open_jtalk"):
    if not shutil.which(command): raise SystemExit(f"Missing command: {command}")
dictionary = next(iter(Path("/var/lib/mecab/dic/open-jtalk").glob("*")), None)
voice = next(iter(Path("/usr/share/hts-voice").rglob("*.htsvoice")), None)
if not dictionary or not voice: raise SystemExit("Open JTalk dictionary/voice not found")
output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp); wav = tmp / "voice.wav"; ass = tmp / "captions.ass"; text = tmp / "narration.txt"
    text.write_text("".join(c["narration"] for c in story["script"]))
    subprocess.run(["open_jtalk", "-x", str(dictionary), "-m", str(voice), "-r", "1.12", "-ow", str(wav), str(text)], check=True)
    def stamp(seconds):
        cs = round(seconds * 100); return f"{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}"
    header = "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,Noto Sans CJK JP,76,&H00FFFFFF,&H00FFFFFF,&H00101010,&H88000000,-1,0,0,0,100,100,0,0,3,4,0,2,90,90,280,1\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    events = []
    for cue in story["script"]:
        caption = cue["caption"].replace("\n", "\\N").replace(",", "，")
        events.append(f"Dialogue: 0,{stamp(cue['start'])},{stamp(cue['end'])},Default,,0,0,0,,{caption}")
    ass.write_text(header + "\n".join(events) + "\n")
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x111827:s=1080x1920:r=30:d=12", "-i", str(wav), "-vf", f"subtitles={ass}", "-af", "apad=pad_dur=12,loudnorm=I=-16:TP=-1.5:LRA=11", "-t", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
    subprocess.run(cmd, check=True)
print(output)

