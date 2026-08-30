import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DefaultImageModelTest(unittest.TestCase):
    def test_production_default_is_gpt_image_2(self):
        config = json.loads((ROOT / "config/image-generation.json").read_text())
        self.assertEqual(config["model"], "gpt-image-2")

    def test_generation_script_reads_model_from_config(self):
        source = (ROOT / "scripts/generate_story_images.py").read_text()
        self.assertIn('"model": CONFIG["model"]', source)


if __name__ == "__main__":
    unittest.main()
