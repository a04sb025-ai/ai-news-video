import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DefaultImageModelTest(unittest.TestCase):
    def test_production_default_is_gpt_image_2(self):
        config = json.loads((ROOT / "config/image-generation.json").read_text())
        self.assertEqual(config["model"], "gpt-image-2")

    def test_production_default_quality_is_low(self):
        config = json.loads((ROOT / "config/image-generation.json").read_text())
        self.assertEqual(config["quality"], "low")

    def test_finished_opening_uses_separate_medium_profile(self):
        config = json.loads((ROOT / "config/image-generation.json").read_text())
        opening = config["opening_thumbnail"]
        self.assertTrue(opening["enabled"])
        self.assertEqual(opening["model"], "gpt-image-2")
        self.assertEqual(opening["size"], "864x1536")
        self.assertEqual(opening["quality"], "medium")
        self.assertEqual(opening["asset_name"], "opening-thumbnail.png")

    def test_generation_script_keeps_body_model_and_reads_opening_profile(self):
        source = (ROOT / "scripts/generate_story_images.py").read_text()
        self.assertIn('"model": CONFIG["model"]', source)
        self.assertIn("opening_thumbnail_profile()", source)
        self.assertIn("OPENING_THUMBNAIL_MODEL", source)
        self.assertIn("OPENING_THUMBNAIL_QUALITY", source)


if __name__ == "__main__":
    unittest.main()
