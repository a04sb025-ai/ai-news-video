import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AllSceneSplitLayoutTest(unittest.TestCase):
    def test_non_opening_images_reserve_lower_text_safe_zone(self):
        source = (ROOT / "scripts/generate_story_images.py").read_text()
        self.assertIn("BODY_LAYOUT = (", source)
        self.assertIn("lower 42 percent", source)
        self.assertIn("between 8 and 54 percent", source)
        self.assertIn("else BODY_LAYOUT", source)
        self.assertIn("one-page-one-message", source)
        self.assertIn("daily-editorial-v5-all-scenes-split-text-visual", source)

    def test_body_renderer_uses_reserved_space_without_large_overlay(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertNotIn("rect_path(42, 1110, 996, 620)", renderer)
        self.assertIn('BODY_LAYOUT_CONTRACT = "split-text-visual-v1"', renderer)
        self.assertIn(r"\pos(90,1105)", renderer)
        self.assertIn('"body_large_overlay_panel": False', renderer)
        self.assertIn('"body_generated_image_full_frame": True', renderer)
        self.assertIn('"body_text_safe_area_ratio": {"top": 0.58, "bottom": 0.91}', renderer)


if __name__ == "__main__":
    unittest.main()
