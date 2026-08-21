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
if __name__ == "__main__": unittest.main()
