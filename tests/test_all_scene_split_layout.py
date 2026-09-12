import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AllSceneSplitLayoutTest(unittest.TestCase):
    def test_non_opening_images_reserve_shorts_safe_copy_zone(self):
        source = (ROOT / "scripts/generate_story_images.py").read_text()
        self.assertIn("BODY_LAYOUT = (", source)
        self.assertIn("from 38 to 70 percent", source)
        self.assertIn("bottom 30 percent", source)
        self.assertIn("rightmost 18 percent", source)
        self.assertIn("between 8 and 36 percent", source)
        self.assertIn("else BODY_LAYOUT", source)
        self.assertIn("one-page-one-message", source)
        self.assertIn("daily-editorial-v6-shorts-ui-safe", source)

    def test_body_renderer_keeps_critical_copy_above_platform_metadata(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertIn('BODY_LAYOUT_CONTRACT = "youtube-shorts-ui-safe-v2"', renderer)
        self.assertIn('SHORTS_UI_SAFE_AREA = {"left": 72, "right": 888, "top": 160, "bottom": 1344}', renderer)
        self.assertIn('SHORTS_UI_EXCLUSION = {"top": 160, "right": 192, "bottom": 576, "left": 72}', renderer)
        self.assertIn('BODY_TEXT_AREA = {"left": 72, "right": 888, "top": 742, "bottom": 1328}', renderer)
        self.assertIn(r"\pos(72,760)", renderer)
        self.assertIn(r"\pos(72,820)", renderer)
        self.assertIn(r"\pos(72,970)", renderer)
        self.assertIn(r"\pos(72,1090)", renderer)
        self.assertNotIn(r"\pos(90,1480)", renderer)
        self.assertIn('"youtube_shorts_ui_safe_area_px": SHORTS_UI_SAFE_AREA', renderer)
        self.assertIn('"body_large_overlay_panel": False', renderer)
        self.assertIn('"body_generated_image_full_frame": True', renderer)
        self.assertIn('"body_text_safe_area_ratio": {"left": 0.067, "right": 0.822, "top": 0.386, "bottom": 0.692}', renderer)
        self.assertIn("def add_opening_body_page", renderer)
        self.assertIn("add_opening_body_page(events, cue, OPENING_END, end)", renderer)

    def test_opening_copy_starts_below_top_app_chrome(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertIn(r"\pos(92,175)", renderer)
        self.assertIn(r"\pos(90,175)", renderer)
        self.assertIn(r"\pos(86,170)", renderer)
        self.assertNotIn(r"\pos(86,145)", renderer)


if __name__ == "__main__":
    unittest.main()
