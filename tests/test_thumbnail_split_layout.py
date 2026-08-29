import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ThumbnailSplitLayoutTest(unittest.TestCase):
    def test_opening_image_prompt_reserves_text_and_visual_zones(self):
        source = (ROOT / "scripts/generate_story_images.py").read_text()
        self.assertIn("top 38 percent", source)
        self.assertIn("fully below 42 percent", source)
        self.assertIn("lower-left corner relatively quiet", source)
        self.assertIn("do not paint a title card, dark text panel, banner, box", source)
        self.assertIn("daily-editorial-v5-all-scenes-split-text-visual", source)

    def test_renderer_does_not_cover_opening_with_large_dark_panels(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertNotIn('rect_path(36, 118, 1008, 660)', renderer)
        self.assertNotIn('rect_path(48, 175, 984, 590)', renderer)
        self.assertNotIn('rect_path(40, 120, 1000, 620)', renderer)
        self.assertIn('OPENING_LAYOUT_CONTRACT = "split-text-visual-v1"', renderer)
        self.assertIn('"opening_large_overlay_panel": False', renderer)
        self.assertIn('"opening_generated_image_full_frame": True', renderer)

    def test_brand_stays_inside_text_safe_zone_instead_of_covering_main_visual(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertIn(r'\pos(92,620)', renderer)
        self.assertIn(r'\pos(88,630)', renderer)
        self.assertIn(r'\pos(90,650)', renderer)


if __name__ == "__main__":
    unittest.main()
