import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class YouTubeShortsSafeAreaTest(unittest.TestCase):
    def test_renderer_records_conservative_1080x1920_safe_area(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertIn('SHORTS_UI_SAFE_AREA = {"left": 72, "right": 888, "top": 160, "bottom": 1344}', renderer)
        self.assertIn('SHORTS_UI_EXCLUSION = {"top": 160, "right": 192, "bottom": 576, "left": 72}', renderer)
        self.assertIn('BODY_TEXT_AREA = {"left": 72, "right": 888, "top": 742, "bottom": 1328}', renderer)
        self.assertIn('"youtube_shorts_ui_safe_area_px": SHORTS_UI_SAFE_AREA', renderer)
        self.assertIn('"youtube_shorts_ui_exclusion_px": SHORTS_UI_EXCLUSION', renderer)

    def test_body_copy_is_moved_out_of_lower_metadata_zone(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        for safe_position in (r"\pos(72,760)", r"\pos(72,820)", r"\pos(72,970)", r"\pos(72,1090)"):
            self.assertIn(safe_position, renderer)
        for old_unsafe_position in (r"\pos(90,1105)", r"\pos(90,1170)", r"\pos(90,1360)", r"\pos(90,1480)"):
            self.assertNotIn(old_unsafe_position, renderer)
        self.assertIn("Style: SectionHeadline,Noto Sans CJK JP,60", renderer)
        self.assertIn("Style: Subtitle,Noto Sans CJK JP,48", renderer)

    def test_generated_art_reserves_the_same_safe_band(self):
        generator = (ROOT / "scripts/generate_story_images.py").read_text()
        self.assertIn("from 38 to 70 percent", generator)
        self.assertIn("bottom 30 percent", generator)
        self.assertIn("rightmost 18 percent", generator)
        self.assertIn("between 8 and 36 percent", generator)


if __name__ == "__main__":
    unittest.main()
