import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ThumbnailSplitLayoutTest(unittest.TestCase):
    def test_finished_opening_prompt_removes_legacy_thumbnail_constraints(self):
        source = (ROOT / "scripts/generate_story_images.py").read_text()
        self.assertIn("complete final opening thumbnail as one integrated vertical Japanese AI-news poster", source)
        self.assertIn("Do not reserve an empty typography zone", source)
        self.assertIn("Visible Japanese text is allowed and required", source)
        self.assertIn("wordmark, or logo may appear only when that entity is explicitly named", source)
        self.assertIn('top-left small label "今朝のAIニュース"', source)
        self.assertIn('top-right small brand "AIツールウォッチ"', source)
        self.assertIn("daily-editorial-v8-finished-opening", source)

    def test_legacy_scene_one_still_reserves_space_for_post_thumbnail_explanation(self):
        source = (ROOT / "scripts/generate_story_images.py").read_text()
        self.assertIn("top 44 percent", source)
        self.assertIn("fully below 46 percent", source)
        self.assertIn("lower-left corner relatively quiet", source)
        self.assertIn("poster-grade vertical editorial key art", source)

    def test_renderer_uses_finished_poster_untouched_when_available(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertIn('OPENING_LAYOUT_CONTRACT = "generated-complete-poster-v1" if USE_FINISHED_OPENING else "split-text-visual-v1"', renderer)
        self.assertIn("if USE_FINISHED_OPENING:", renderer)
        self.assertIn('finished_opening_index = None', renderer)
        self.assertIn("[finishedopening]", renderer)
        self.assertIn('"opening_thumbnail_source": "generated-complete-poster-v1" if USE_FINISHED_OPENING else "renderer-composed-opening-v1"', renderer)
        self.assertIn('"opening_finished_thumbnail": USE_FINISHED_OPENING', renderer)

    def test_legacy_renderer_typography_remains_as_fallback(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertIn(r'\pos(92,640)', renderer)
        self.assertIn(r'\pos(88,650)', renderer)
        self.assertIn(r'\pos(90,650)', renderer)
        self.assertIn('"opening_large_overlay_panel": False', renderer)


if __name__ == "__main__":
    unittest.main()
