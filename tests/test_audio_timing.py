import math
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

from scripts.audio_timing import (
    align_subtitle_segments,
    detect_silence_regions,
    ensure_terminal_pause,
    proportional_boundary_targets,
    snap_scene_boundaries,
    split_subtitle_text,
)


def write_test_wav(path: Path, sections, sample_rate=1000):
    samples = array("h")
    phase = 0
    for duration, amplitude in sections:
        frames = round(duration * sample_rate)
        for _ in range(frames):
            if amplitude:
                value = round(amplitude * math.sin(2 * math.pi * 40 * phase / sample_rate))
            else:
                value = 0
            samples.append(value)
            phase += 1
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(samples.tobytes())


class AudioTimingTest(unittest.TestCase):
    def test_terminal_pause_is_added_without_changing_spoken_words(self):
        self.assertEqual(ensure_terminal_pause("これはテストです"), "これはテストです。")
        self.assertEqual(ensure_terminal_pause("これはテストです。"), "これはテストです。")
        self.assertEqual(ensure_terminal_pause("本当？"), "本当？")

    def test_detects_real_silence_regions_in_final_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            wav_path = Path(directory) / "voice.wav"
            write_test_wav(wav_path, [
                (1.0, 5000), (0.20, 0),
                (1.0, 5000), (0.16, 0),
                (1.0, 5000),
            ])
            regions = detect_silence_regions(wav_path)
        internal = [region for region in regions if 0.5 < region["start"] < 2.5]
        self.assertGreaterEqual(len(internal), 2)
        self.assertAlmostEqual(internal[0]["start"], 1.0, delta=0.03)
        self.assertAlmostEqual(internal[0]["end"], 1.2, delta=0.03)
        self.assertAlmostEqual(internal[1]["start"], 2.2, delta=0.03)
        self.assertAlmostEqual(internal[1]["end"], 2.36, delta=0.03)

    def test_scene_boundaries_snap_to_nearby_final_wav_pauses(self):
        probes = [1.0, 1.0, 1.0]
        duration = 3.36
        targets = proportional_boundary_targets(probes, duration)
        regions = [
            {"start": 1.0, "end": 1.20, "duration": 0.20},
            {"start": 2.20, "end": 2.36, "duration": 0.16},
        ]
        boundaries, details = snap_scene_boundaries(probes, duration, regions)
        self.assertEqual(len(boundaries), 2)
        self.assertEqual([item["method"] for item in details], ["silence-snapped", "silence-snapped"])
        self.assertAlmostEqual(boundaries[0], 1.12, delta=0.01)
        self.assertAlmostEqual(boundaries[1], 2.32, delta=0.01)
        self.assertLess(abs(boundaries[0] - targets[0]), 0.2)
        self.assertLess(abs(boundaries[1] - targets[1]), 0.2)


    def test_subtitle_text_prefers_authored_phrase_boundaries(self):
        chunks = split_subtitle_text("最初の説明です。次の説明です。最後です。", max_chunks=3)
        self.assertEqual(chunks, ["最初の説明です。", "次の説明です。", "最後です。"])

    def test_subtitle_segments_snap_phrase_changes_to_final_wav_pauses(self):
        regions = [
            {"start": 1.8, "end": 2.1, "duration": 0.3},
            {"start": 3.8, "end": 4.1, "duration": 0.3},
        ]
        segments = align_subtitle_segments(
            "最初の説明です。次の説明です。最後です。",
            0.0,
            6.0,
            regions,
        )
        self.assertEqual(len(segments), 3)
        self.assertAlmostEqual(segments[0]["end"], 1.88, delta=0.02)
        self.assertAlmostEqual(segments[1]["end"], 3.88, delta=0.02)
        self.assertEqual("".join(segment["text"] for segment in segments), "最初の説明です。次の説明です。最後です。")


    def test_far_silence_is_not_used_for_wrong_scene(self):
        probes = [1.0, 1.0, 1.0]
        boundaries, details = snap_scene_boundaries(
            probes,
            6.0,
            [{"start": 4.7, "end": 5.0, "duration": 0.3}],
            search_seconds=0.5,
        )
        self.assertEqual(details[0]["method"], "proportional-fallback")
        self.assertAlmostEqual(boundaries[0], 2.0, delta=0.01)


if __name__ == "__main__":
    unittest.main()
