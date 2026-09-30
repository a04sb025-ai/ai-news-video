import unittest

from scripts.render_adaptive_explainer_fast import optimize_ffmpeg_command


class FastAdaptiveRendererTest(unittest.TestCase):
    def test_static_inputs_keep_30fps_to_avoid_framesync_flash(self):
        command = [
            "ffmpeg",
            "-loop", "1", "-framerate", "30", "-i", "scene.png",
            "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
            "output.mp4",
        ]

        optimized, metadata = optimize_ffmpeg_command(command)

        framerate_index = optimized.index("-framerate")
        self.assertEqual(optimized[framerate_index + 1], "30")
        self.assertEqual(metadata["still_inputs_retimed"], 0)
        self.assertEqual(metadata["still_inputs_preserved_30fps"], 1)
        self.assertEqual(optimized[optimized.index("-preset") + 1], "veryfast")
        self.assertIn("-crf", optimized)
        self.assertEqual(optimized[optimized.index("-crf") + 1], "21")


if __name__ == "__main__":
    unittest.main()
