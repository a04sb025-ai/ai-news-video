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

from audio_timing import detect_silence_regions, ensure_terminal_pause, snap_scene_boundaries
from narration_tts import synthesize_published_narration, wav_duration

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
BODY_LAYOUT_CONTRACT = "youtube-shorts-ui-safe-v2"
THUMBNAIL_RENDER_SECONDS = min(0.5, max(0.1, OPENING_END / 2))

# Published production narration uses one natural TTS pass. Open JTalk remains
# available for deterministic offline CI and scene-only timing probes, but its
# local phrase-final duration artifacts are no longer allowed into production
# whenever OPENAI_API_KEY is configured.
OPEN_JTALK_RATE = 1.10
FINAL_END_PAUSE_SECONDS = 0.18
MAX_RENDER_DURATION_SECONDS = 15 * 60

# YouTube Shorts overlays are not part of the encoded video, so critical copy must
# stay away from the app chrome. These values are deliberately conservative for
# the 1080x1920 master. The bottom progress bar is decorative and may sit outside.
SHORTS_UI_SAFE_AREA = {"left": 72, "right": 888, "top": 160, "bottom": 1344}
SHORTS_UI_EXCLUSION = {"top": 160, "right": 192, "bottom": 576, "left": 72}
BODY_TEXT_AREA = {"left": 72, "right": 888, "top": 742, "bottom": 1328}


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
    """Keep every important body-text layer above Shorts metadata and left of the action rail."""
    if end <= start:
        return
    fade_tag = r"\fad(100,100)" if fade else ""
    events.append(vector(start, end, rect_path(72, 742, 180, 8), "58D6FF", fade_tag, 4))
    events.append(dialogue(start, end, "Eyebrow", cue["label"], rf"\pos(72,760){fade_tag}", 5))
    events.append(dialogue(start, end, "SectionHeadline", cue["caption"], rf"\pos(72,820){fade_tag}", 6))
    events.append(dialogue(start, end, "Support", cue["support_text"], rf"\pos(72,970){fade_tag}", 6))
    events.append(dialogue(start, end, "Subtitle", cue["subtitle"], rf"\pos(72,1090){fade_tag}", 7))


def add_opening_body_page(events, cue, start, end):
    """After the thumbnail window, keep copy inside the opening image's top text-safe zone."""
    if end <= start:
        return
    fade_tag = r"\fad(100,100)"
    events.append(vector(start, end, rect_path(90, 170, 180, 8), "58D6FF", fade_tag, 4))
    events.append(dialogue(start, end, "Eyebrow", cue["label"], rf"\pos(90,188){fade_tag}", 5))
    events.append(dialogue(start, end, "SectionHeadline", cue["caption"], rf"\pos(90,250)\fs64{fade_tag}", 6))
    events.append(dialogue(start, end, "Support", cue["support_text"], rf"\pos(90,425)\fs40{fade_tag}", 6))
    events.append(dialogue(start, end, "Subtitle", cue["subtitle"], rf"\pos(90,535)\fs44{fade_tag}", 7))


def add_opening(events, cue):
    """Place typography in the generated image's reserved negative space without masking the artwork."""
    start, end = 0.0, OPENING_END
    if OPENING_STYLE == "A":
        events.append(vector(start, end, rect_path(62, 190, 18, 455), "00A5FF", layer=4))
        events.append(vector(start, end, rect_path(82, 685, 900, 10), "00A5FF", layer=4))
        events.append(dialogue(start, end, "Eyebrow", "AI NEWS", r"\pos(92,175)\1c&H00A5FF&", 5))
        events.append(dialogue(start, end, "OpeningHeadline", cue["caption"], r"\pos(110,255)\fs108\bord10\3c&H08111F&", 7))
        events.append(dialogue(start, end, "OpeningBrand", "AIツールウォッチ", r"\pos(92,640)", 8))
    elif OPENING_STYLE == "C":
        events.append(vector(start, end, rect_path(88, 225, 185, 8), "C87CFF", layer=4))
        events.append(dialogue(start, end, "Eyebrow", "AI NEWS", r"\pos(90,175)\1c&HC87CFF&", 5))
        events.append(dialogue(start, end, "OpeningHeadline", cue["caption"], r"\pos(90,285)\fs120\bord9\3c&H101528&", 7))
        events.append(dialogue(start, end, "OpeningBrand", "AIツールウォッチ", r"\pos(90,650)", 8))
    else:
        events.append(vector(start, end, rect_path(78, 210, 250, 8), "00A5FF", layer=4))
        events.append(vector(start, end, rect_path(338, 210, 112, 8), "C87CFF", layer=4))
        events.append(dialogue(start, end, "Eyebrow", "AI NEWS", r"\pos(86,170)", 5))
        events.append(dialogue(start, end, "OpeningHeadline", cue["caption"], r"\pos(88,275)\fs106\bord9\3c&H101528&", 7))
        events.append(dialogue(start, end, "OpeningBrand", "AIツールウォッチ", r"\pos(88,650)", 8))


def render_opening_thumbnail(ass, destination):
    """Compose the canonical thumbnail directly from source artwork and opening typography.

    This deliberately does not sample the finished MP4, so video startup frames, fades,
    codec timing, or player behavior cannot change the YouTube thumbnail.
    """
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=0x18213A:s={WIDTH}x{HEIGHT}:r={FPS}:d=1",
    ]
    input_index = 1
    first_image_index = None
    mozo_index = None
    if USE_STORY_IMAGES:
        first_image_index = input_index
        command.extend(["-loop", "1", "-framerate", str(FPS), "-i", str(STORY_IMAGES[0])])
        input_index += 1
    if USE_MOZO_OPENING_ASSET:
        mozo_index = input_index
        command.extend(["-loop", "1", "-framerate", str(FPS), "-i", str(MOZO_OPENING_ASSET)])

    filters = []
    current = "[0:v]"
    if first_image_index is not None:
        filters.append(
            f"[{first_image_index}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},setsar=1[thumbscene];"
        )
        filters.append(f"{current}[thumbscene]overlay=0:0[thumbart];")
        current = "[thumbart]"
    if mozo_index is not None:
        filters.append(f"[{mozo_index}:v]scale=190:-1[thumbmozo];")
        filters.append(f"{current}[thumbmozo]overlay=72:1480[thumbwithmozo];")
        current = "[thumbwithmozo]"
    filters.append(f"{current}subtitles={ass}[thumbnail]")

    command.extend([
        "-filter_complex", "".join(filters),
        "-map", "[thumbnail]",
        "-ss", str(THUMBNAIL_RENDER_SECONDS),
        "-frames:v", "1",
        "-q:v", "2",
        str(destination),
    ])
    subprocess.run(command, check=True)
    if not destination.is_file() or destination.stat().st_size <= 0:
        raise SystemExit("Opening thumbnail render did not produce an image")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(destination),
        "-f", "null", "-",
    ], check=True)


output.parent.mkdir(parents=True, exist_ok=True)
temporary_output = output.with_name(f".{output.stem}.rendering{output.suffix}")
thumbnail_output = output.with_name(f"{output.stem}.thumbnail.jpg")
temporary_thumbnail = output.with_name(f".{output.stem}.rendering-thumbnail.jpg")
temporary_output.unlink(missing_ok=True)
temporary_thumbnail.unlink(missing_ok=True)

with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    wav = tmp / "voice.wav"
    ass = tmp / "adaptive-explainer.ass"
    probe_durations = []

    # Probe each cue only to estimate where its matching pause should occur. These
    # files are never concatenated or published; only the one continuous WAV below
    # is audible in the finished video.
    for index, cue in enumerate(story["script"]):
        probe_text = tmp / f"probe-{index}.txt"
        probe_wav = tmp / f"probe-{index}.wav"
        probe_text.write_text(ensure_terminal_pause(cue["narration"]) + "\n")
        subprocess.run([
            "open_jtalk", "-x", str(dictionary), "-m", str(voice), "-r", str(OPEN_JTALK_RATE),
            "-ow", str(probe_wav), str(probe_text),
        ], check=True)
        with wave.open(str(probe_wav)) as audio:
            probe_durations.append(audio.getnframes() / audio.getframerate())

    # Synthesize the only narration that reaches the published video in one pass.
    # Production uses natural TTS when the API key is present. Offline CI uses
    # Open JTalk so the render suite stays deterministic and network-free.
    narration = tmp / "narration.txt"
    narration_wav = tmp / "voice-single-pass.wav"
    narration_chunks = [ensure_terminal_pause(cue["narration"]) for cue in story["script"]]
    narration_text = " ".join(narration_chunks)
    narration.write_text(narration_text + "\n")
    tts_metadata = synthesize_published_narration(
        narration_text,
        narration_wav,
        dictionary=dictionary,
        voice=voice,
        open_jtalk_rate=OPEN_JTALK_RATE,
    )
    narration_duration = float(tts_metadata["duration_seconds"])
    physical_narration_duration = wav_duration(narration_wav)
    if abs(narration_duration - physical_narration_duration) > 0.5:
        raise SystemExit(
            "Narration duration metadata disagrees with the physical WAV: "
            f"metadata={narration_duration:.3f}s physical={physical_narration_duration:.3f}s"
        )
    if narration_duration > MAX_RENDER_DURATION_SECONDS:
        raise SystemExit(
            f"Refusing runaway render duration: {narration_duration:.3f}s "
            f"(limit={MAX_RENDER_DURATION_SECONDS}s)"
        )
    print(
        f"[render-timing] narration_seconds={narration_duration:.3f} "
        f"physical_wav_seconds={physical_narration_duration:.3f}",
        flush=True,
    )

    probe_total = sum(probe_durations)
    if probe_total <= 0 or narration_duration <= 0:
        raise SystemExit("TTS produced an empty narration")

    # Use rough probe proportions only to identify the expected neighborhood, then
    # snap each scene boundary to a real low-energy pause measured in the final WAV.
    # The published speech itself is never stretched or compressed after synthesis.
    silence_regions = detect_silence_regions(narration_wav)
    scene_boundaries, boundary_alignment = snap_scene_boundaries(
        probe_durations,
        narration_duration,
        silence_regions,
    )
    timeline = [0.0, *scene_boundaries, narration_duration + FINAL_END_PAUSE_SECONDS]
    cue_durations = []
    for index, cue in enumerate(story["script"]):
        start = round(timeline[index], 4)
        end = round(timeline[index + 1], 4)
        cue["start"] = start
        cue["end"] = end
        cue_durations.append(round(end - start, 4))

    DURATION = round(narration_duration + FINAL_END_PAUSE_SECONDS, 4)
    story["expected_duration_seconds"] = round(DURATION, 2)
    OPENING_END = min(3.0, float(story["script"][0]["end"]))
    THUMBNAIL_RENDER_SECONDS = min(0.5, max(0.1, OPENING_END / 2))
    story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n")

    # Copy the single-pass narration unchanged and add only final padding. There is
    # deliberately no atempo and no concatenation of per-scene speech.
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(narration_wav),
        "-af", f"apad=pad_dur={FINAL_END_PAUSE_SECONDS},atrim=duration={DURATION}", str(wav),
    ], check=True)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Eyebrow,Noto Sans CJK JP,40,&H00FFF1C7,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,4,0,1,0,0,7,72,192,105,1
Style: OpeningHeadline,Noto Sans CJK JP,106,&H00FFFFFF,&H00FFFFFF,&H00009BFF,&H00101528,-1,0,0,0,100,100,0,0,1,8,3,7,90,90,210,1
Style: OpeningBrand,Noto Sans CJK JP,34,&H00FFFFFF,&H00FFFFFF,&H00101528,&H00101528,-1,0,0,0,100,100,2,0,1,3,0,7,70,70,0,1
Style: OpeningSubtitle,Noto Sans CJK JP,46,&H00FFFFFF,&H00FFFFFF,&H00101528,&H00101528,-1,0,0,0,100,100,0,0,3,2,0,7,30,30,0,1
Style: SectionHeadline,Noto Sans CJK JP,60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,72,192,0,1
Style: Support,Noto Sans CJK JP,48,&H00FFF1C7,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,72,192,0,1
Style: Subtitle,Noto Sans CJK JP,48,&H00FFFFFF,&H00FFFFFF,&H00101528,&H00101528,-1,0,0,0,100,100,0,0,3,2,0,7,72,192,0,1
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
            add_opening_body_page(events, cue, OPENING_END, end)
        elif index < len(page_cues):
            add_body_page(events, cue, start, end)
        else:
            events.append(vector(start, end, rect_path(190, 760, 700, 8), "58D6FF", r"\fad(100,120)", 2))
            events.append(dialogue(start, end, "Outro", "今日のAIニュース", r"\pos(540,880)\fs58\fad(100,120)", 3))
            events.append(dialogue(start, end, "Outro", "AIツールウォッチ", r"\pos(540,1000)\fs50\1c&H58D6FF&\fad(100,120)", 3))

    ass.write_text(header + "\n".join(events) + "\n")
    render_opening_thumbnail(ass, temporary_thumbnail)

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
    print(
        f"[render-timing] main_ffmpeg_target_seconds={DURATION:.3f} "
        f"story_images={len(STORY_IMAGES) if USE_STORY_IMAGES else 0}",
        flush=True,
    )
    try:
        subprocess.run(command, check=True)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(temporary_output),
            "-map", "0", "-f", "null", "-",
        ], check=True)
        temporary_thumbnail.replace(thumbnail_output)
        temporary_output.replace(output)
    finally:
        temporary_output.unlink(missing_ok=True)
        temporary_thumbnail.unlink(missing_ok=True)

manifest = {
    "renderer": "adaptive-explainer-v3-shorts-safe",
    "content_hash": story.get("content_hash"),
    "page_count": len(story.get("script", [])) - 1,
    "duration_seconds": DURATION,
    "audio_pipeline": "single-pass-natural-tts-audio-led-v4",
    "audio_tts_provider": tts_metadata["provider"],
    "audio_tts_model": tts_metadata["model"],
    "audio_tts_voice": tts_metadata["voice"],
    "audio_tts_rate": tts_metadata["speed"],
    "audio_open_jtalk_probe_rate": OPEN_JTALK_RATE,
    "audio_single_pass": True,
    "audio_single_pass_duration_seconds": round(narration_duration, 4),
    "audio_alignment_source": "single-pass-wav-silence-snapped",
    "audio_probe_durations": [round(duration, 4) for duration in probe_durations],
    "audio_detected_silence_regions": [
        {key: round(float(value), 4) for key, value in region.items()}
        for region in silence_regions
    ],
    "audio_scene_boundaries": [round(boundary, 4) for boundary in scene_boundaries],
    "audio_boundary_alignment": boundary_alignment,
    "audio_alignment_fallback_count": sum(
        1 for item in boundary_alignment if item["method"] == "proportional-fallback"
    ),
    "audio_scene_durations": cue_durations,
    "audio_final_end_pause_seconds": FINAL_END_PAUSE_SECONDS,
    "audio_tempo_adjustment": False,
    "full_narration_subtitles": True,
    "subtitle_font_size_px": 48,
    "opening_subtitle_font_size_px": 46,
    "opening_headline_font_size_px": {"A": 108, "B": 106, "C": 120}[OPENING_STYLE],
    "opening_headline_target_chars_per_line": 9,
    "opening_thumbnail_style": OPENING_STYLE,
    "opening_support_copy_visible": False,
    "opening_subtitle_visible": False,
    "opening_single_dominant_visual": True,
    "opening_thumbnail_window_seconds": OPENING_END,
    "opening_layout_contract": OPENING_LAYOUT_CONTRACT,
    "opening_text_safe_area_ratio": {"top": 0.08, "bottom": 0.40},
    "opening_dominant_visual_area_ratio": {"top": 0.42, "bottom": 0.82},
    "opening_large_overlay_panel": False,
    "opening_generated_image_full_frame": True,
    "opening_thumbnail_file": str(thumbnail_output),
    "opening_thumbnail_source": "renderer-composed-opening-v1",
    "opening_thumbnail_direct_render": True,
    "opening_thumbnail_width": WIDTH,
    "opening_thumbnail_height": HEIGHT,
    "opening_thumbnail_render_seconds": THUMBNAIL_RENDER_SECONDS,
    "opening_thumbnail_sha256": hashlib.sha256(thumbnail_output.read_bytes()).hexdigest(),
    "body_layout_contract": BODY_LAYOUT_CONTRACT,
    "youtube_shorts_ui_safe_area_px": SHORTS_UI_SAFE_AREA,
    "youtube_shorts_ui_exclusion_px": SHORTS_UI_EXCLUSION,
    "body_text_safe_area_px": BODY_TEXT_AREA,
    "body_text_safe_area_ratio": {"left": 0.067, "right": 0.822, "top": 0.386, "bottom": 0.692},
    "body_dominant_visual_area_ratio": {"top": 0.08, "bottom": 0.36},
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
