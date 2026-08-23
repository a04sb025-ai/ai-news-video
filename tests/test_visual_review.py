import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("visual_review", ROOT / "scripts/review_visual_quality.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class VisualReviewTest(unittest.TestCase):
    def test_collect_frames_orders_zero_to_final_opening_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("opening-2.967s.png", "opening-1s.png", "opening-0s.png", "opening-2s.png"):
                (root / name).write_bytes(b"png")
            self.assertEqual(
                [path.name for path in review.collect_frames(root)],
                ["opening-0s.png", "opening-1s.png", "opening-2s.png", "opening-2.967s.png"],
            )

    def test_parse_json_object_accepts_fenced_json(self):
        parsed = review.parse_json_object('```json\n{"scores":{"x":1}}\n```')
        self.assertEqual(parsed["scores"]["x"], 1)

    def test_normalize_review_requires_all_six_scores_and_one_improvement(self):
        raw = {
            "scores": {key: 8 for key in review.SCORE_KEYS},
            "safe_to_keep_publishing": True,
            "priority_improvement": "中央カードをニュース固有の図解にする",
            "rationale": "汎用カードより内容理解が速くなるため",
            "likely_files": ["scripts/render_reference.py", "not-allowed.txt"],
            "current_strengths": ["もぞが安定", "見出しが読みやすい"],
        }
        result = review.normalize_review(raw, {"request_id": "x", "template": "B", "engine_sha": "abc"})
        self.assertEqual(result["average_score"], 8.0)
        self.assertEqual(result["likely_files"], ["scripts/render_reference.py"])
        self.assertTrue(result["safe_to_keep_publishing"])

    def test_markdown_enforces_one_change_and_keeps_daily_publish_independent(self):
        data = {
            "status": "ok",
            "average_score": 7.5,
            "request_id": "x",
            "template": "B",
            "engine_sha": "abc",
            "safe_to_keep_publishing": True,
            "scores": {key: 7.5 for key in review.SCORE_KEYS},
            "priority_improvement": "もぞを少し大きくする",
            "rationale": "シリーズ感を強める",
            "likely_files": ["scripts/render_reference.py"],
            "current_strengths": ["読みやすい"],
        }
        markdown = review.render_markdown(data)
        self.assertIn("今週の改善は1件だけ", markdown)
        self.assertIn("日次公開はこの改善レビューから独立", markdown)
        self.assertIn("auto_publish_ready", markdown)

    def test_workflow_is_weekly_and_non_blocking_to_production(self):
        workflow = (ROOT / ".github/workflows/weekly-visual-improvement.yml").read_text()
        self.assertIn('cron: "40 23 * * 0"', workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("issues: write", workflow)
        self.assertNotIn("git push origin HEAD:main", workflow)
        self.assertNotIn("merge", workflow.lower())


if __name__ == "__main__":
    unittest.main()
