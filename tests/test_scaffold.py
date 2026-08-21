import json, subprocess, sys, unittest
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
if __name__ == "__main__": unittest.main()
