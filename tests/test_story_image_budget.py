import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("generate_story_images", ROOT / "scripts/generate_story_images.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class StoryImageBudgetTest(unittest.TestCase):
    def test_adaptive_story_can_request_up_to_ten_scene_visuals(self):
        self.assertEqual(module.MAX_IMAGES, 10)
        scenes = []
        assets = []
        for index in range(6):
            scenes.append({
                "role": "reason",
                "visual_type": "flow",
                "verified_content": f"verified scene {index + 1}",
                "visual_intent": "show the concrete relationship",
                "key_visuals": ["subject", "result"],
            })
            assets.append(f"scene-{index + 1}.png")
        story = {
            "image_asset_dir": "assets/generated/test/all-scenes/daily-editorial-v1",
            "image_assets": assets,
            "image_scenes": scenes,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "story.json"
            path.write_text(json.dumps(story))
            _, prompts = module.story_prompts(path)
        self.assertEqual(len(prompts), 6)
        self.assertTrue(all("Visual explanation type: flow" in prompt for prompt in prompts.values()))


if __name__ == "__main__":
    unittest.main()
