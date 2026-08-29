import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ab_test_image_models", ROOT / "scripts/ab_test_image_models.py")
ab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ab)


class ImageModelAbTestTests(unittest.TestCase):
    def fixture(self):
        return {
            "request_id": "ab-example", "content_hash": "abcdef123456",
            "source_url": "https://example.com/source", "article_url": "https://aitoolwatch.jp/example",
            "headline": "新しいAI機能", "summary": "作業方法が変わります", "hook": "何が変わる？",
            "image_scenes": [{"role": "hook", "verified_content": "検証済みの発表", "visual_intent": "主役と変化を示す", "key_visuals": ["主役", "変化"]}],
        }

    def test_prompt_uses_story_context_and_visual_rules(self):
        prompt = ab.build_prompt(self.fixture())
        self.assertIn("新しいAI機能", prompt)
        self.assertIn("検証済みの発表", prompt)
        self.assertIn("do not draw Mozo", prompt)
        self.assertIn("top 38 percent", prompt)

    def test_each_failure_is_logged_and_report_is_still_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            story = root / "story.json"
            story.write_text(json.dumps(self.fixture(), ensure_ascii=False))
            with patch.dict(ab.os.environ, {"OPENAI_API_KEY": "test"}), patch.object(ab, "image_request", side_effect=[b"png", RuntimeError("unsupported model")]), patch.object(ab, "make_preview"):
                status = ab.main(["--story-json", str(story), "--models", "gpt-image-1,gpt-image-2", "--output-root", str(root / "out")])
            output = root / "out/ab-example/abcdef123456"
            log = json.loads((output / "comparison-log.json").read_text())
            self.assertEqual(status, 1)
            self.assertTrue(log["models"][0]["success"])
            self.assertFalse(log["models"][1]["success"])
            self.assertIn("unsupported model", log["models"][1]["error_message"])
            self.assertTrue((output / "comparison-report.md").is_file())


if __name__ == "__main__":
    unittest.main()
