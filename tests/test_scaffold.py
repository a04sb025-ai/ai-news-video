import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
class ScaffoldTest(unittest.TestCase):
    def test_video_contract(self):
        c = json.loads((ROOT / "config/short-ja.json").read_text())
        self.assertEqual((c["canvas"]["width"], c["canvas"]["height"]), (1080, 1920))
        self.assertEqual(c["duration_seconds"], {"min": 10, "max": 15})
        self.assertEqual(c["outro"]["text"], "AIツールウォッチ")
    def test_bad_url_rejected(self):
        p = subprocess.run([sys.executable, ROOT / "scripts/new_story.py", "not-a-url"], capture_output=True)
        self.assertNotEqual(p.returncode, 0)
    def test_prepare_story_with_verified_headline_is_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "story.json"
            subprocess.run([sys.executable, ROOT / "scripts/prepare_story.py", "https://example.com/news", output, "公式発表です"], check=True)
            story = json.loads(output.read_text())
            self.assertEqual(story["claims"][0]["text"], "公式発表です")
            self.assertEqual(story["script"][-1]["caption"], "AIツールウォッチ")
    def test_teen_story_timeline_and_caption_limits(self):
        story = json.loads((ROOT / "config/stories/chatgpt-teens-ja.json").read_text())
        self.assertEqual(story["status"], "ready")
        self.assertEqual(story["published_at"], "2026-08-18T00:00:00Z")
        self.assertEqual(story["source_url"], "https://openai.com/index/introducing-chatgpt-for-teens/")
        self.assertTrue(all(claim["source_url"] == story["source_url"] for claim in story["claims"]))
        self.assertEqual(story["script"][0]["start"], 0)
        self.assertEqual(story["script"][-1]["end"], 12)
        for current, following in zip(story["script"], story["script"][1:]):
            self.assertEqual(current["end"], following["start"])
        for cue in story["script"]:
            lines = cue["caption"].splitlines()
            self.assertLessEqual(len(lines), 2)
            self.assertTrue(all(len(line) <= 18 for line in lines))
    def test_workflow_supports_dedicated_and_generic_rendering(self):
        workflow = (ROOT / ".github/workflows/render-video.yml").read_text()
        self.assertIn("default: teen_chatgpt", workflow)
        self.assertIn("run: make render-teen-news", workflow)
        self.assertIn("if: inputs.render_target == 'generic_url'", workflow)
        self.assertIn("python3 scripts/prepare_story.py", workflow)
        self.assertIn("config/stories/chatgpt-teens-ja.json", workflow)
        self.assertIn("OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}", workflow)
        self.assertIn("continue-on-error: true", workflow)
    def test_image_provider_has_exactly_two_safe_cached_assets(self):
        generator = (ROOT / "scripts/generate_story_images.py").read_text()
        config = json.loads((ROOT / "config/image-generation.json").read_text())
        self.assertEqual(config["provider"], "openai")
        self.assertEqual(config["api_key_env"], "OPENAI_API_KEY")
        self.assertEqual(generator.count('"scene-teen-chat.png":'), 1)
        self.assertEqual(generator.count('"scene-learning-safety.png":'), 1)
        self.assertIn("destination.is_file()", generator)
        self.assertNotIn("print(api_key", generator)
if __name__ == "__main__": unittest.main()
