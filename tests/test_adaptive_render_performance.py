import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/render_adaptive_explainer_fast.py"
SPEC = importlib.util.spec_from_file_location("render_adaptive_explainer_fast", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class AdaptiveRenderPerformanceTest(unittest.TestCase):
    def test_looped_stills_are_not_decoded_at_output_frame_rate(self):
        command = [
            "ffmpeg",
            "-f", "lavfi", "-i", "color=s=1080x1920:r=30:d=53",
            "-loop", "1", "-framerate", "30", "-i", "scene-1.png",
            "-loop", "1", "-framerate", "30", "-i", "scene-2.png",
            "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
            "out.mp4",
        ]
        optimized, metadata = MODULE.optimize_ffmpeg_command(command)

        self.assertEqual(metadata["still_inputs_retimed"], 2)
        self.assertEqual(optimized.count("1"), command.count("1") + 2)
        self.assertNotIn("medium", optimized)
        self.assertIn("veryfast", optimized)
        self.assertIn("-crf", optimized)
        crf_index = optimized.index("-crf")
        self.assertEqual(optimized[crf_index + 1], "21")
        self.assertIn("color=s=1080x1920:r=30:d=53", optimized)

    def test_audio_only_ffmpeg_command_is_unchanged(self):
        command = ["ffmpeg", "-i", "voice.wav", "-af", "apad=pad_dur=0.18", "out.wav"]
        optimized, metadata = MODULE.optimize_ffmpeg_command(command)

        self.assertEqual(optimized, command)
        self.assertEqual(metadata["still_inputs_retimed"], 0)
        self.assertFalse(metadata["x264_preset_changed"])


if __name__ == "__main__":
    unittest.main()
