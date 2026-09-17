#!/usr/bin/env python3
"""Run the adaptive renderer with CPU-safe ffmpeg settings for static artwork.

The adaptive video uses still PNG/JPEG artwork. Feeding those stills to ffmpeg at
30 fps makes ffmpeg decode and scale the same pixels thousands of times even
though the image never changes. This wrapper keeps the encoded master at 30 fps,
but feeds looped still inputs at 1 fps so framesync repeats the static frame.
It also swaps the main libx264 preset from medium to veryfast while lowering CRF
to 21 so the speedup does not come from intentionally lowering visual quality.
"""
from __future__ import annotations

import runpy
import subprocess
import time
from pathlib import Path
from typing import Sequence

ORIGINAL_RENDERER = Path(__file__).with_name("render_adaptive_explainer.py")


def optimize_ffmpeg_command(command: Sequence[str]) -> tuple[list[str], dict[str, object]]:
    """Return an equivalent command that avoids redundant static-frame work."""
    optimized = [str(part) for part in command]
    still_inputs = 0

    for index in range(max(0, len(optimized) - 3)):
        if (
            optimized[index] == "-loop"
            and optimized[index + 1] == "1"
            and optimized[index + 2] == "-framerate"
            and optimized[index + 3] == "30"
        ):
            optimized[index + 3] = "1"
            still_inputs += 1

    preset_changed = False
    if "-c:v" in optimized and "libx264" in optimized and "-preset" in optimized:
        preset_index = optimized.index("-preset")
        if preset_index + 1 < len(optimized) and optimized[preset_index + 1] == "medium":
            optimized[preset_index + 1] = "veryfast"
            preset_changed = True
            if "-crf" not in optimized:
                insert_at = optimized.index("-pix_fmt") if "-pix_fmt" in optimized else preset_index + 2
                optimized[insert_at:insert_at] = ["-crf", "21"]

    return optimized, {
        "still_inputs_retimed": still_inputs,
        "x264_preset_changed": preset_changed,
    }


def main() -> None:
    original_run = subprocess.run

    def optimized_run(command, *args, **kwargs):
        if isinstance(command, (list, tuple)) and command and Path(str(command[0])).name == "ffmpeg":
            effective, metadata = optimize_ffmpeg_command(command)
            changed = bool(metadata["still_inputs_retimed"] or metadata["x264_preset_changed"])
            started = time.monotonic()
            if changed:
                print(
                    "[render-optimization] "
                    f"still_inputs_30fps_to_1fps={metadata['still_inputs_retimed']} "
                    f"x264_veryfast={metadata['x264_preset_changed']}",
                    flush=True,
                )
            completed = original_run(effective, *args, **kwargs)
            if changed:
                print(
                    f"[render-optimization] ffmpeg_completed_seconds={time.monotonic() - started:.1f}",
                    flush=True,
                )
            return completed
        return original_run(command, *args, **kwargs)

    subprocess.run = optimized_run
    try:
        runpy.run_path(str(ORIGINAL_RENDERER), run_name="__main__")
    finally:
        subprocess.run = original_run


if __name__ == "__main__":
    main()
