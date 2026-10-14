import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


story_engine = load_module("adaptive_daily_story_trial", "scripts/adaptive_daily_story.py")
image_generator = load_module("story_images_trial", "scripts/generate_story_images.py")
publish_gate = load_module("publish_gate_trial", "scripts/write_automation_result.py")


def example_payload(day):
    roles = ["hook", "context", "definition", "fact", "reason", "impact", "conclusion"]
    pages = [{
        "page_role": role,
        "headline": f"確認済みの要点{i}",
        "support_text": f"検証済みの説明{i}",
        "narration": f"ニュースの説明です。第{i}の話です。",
        "subtitle": f"ニュースの説明です。第{i}の話です。",
        "visual_intent": f"具体的な違い{i}",
        "key_visuals": ["ゲーム", "スマートフォン"],
        "mozo_line": "ここが重要",
        "mozo_usage": "補足",
    } for i, role in enumerate(roles)]
    return {
        "request_id": f"daily-news-{day}-test",
        "source_url": "https://example.com/news",
        "article_url": "https://aitoolwatch.jp/news/",
        "pages": pages,
        "thumbnail_style": "B",
    }


class ThreePosterTrialTest(unittest.TestCase):
    def test_trial_activates_from_october_15_only(self):
        before = story_engine.build_story(example_payload("2026-10-14"))
        after = story_engine.build_story(example_payload("2026-10-15"))
        self.assertEqual(len(before["image_assets"]), 4)
        self.assertEqual(before["production_profile"], "adaptive-legacy")
        self.assertEqual(len(after["image_assets"]), 2)
        self.assertEqual(after["image_assets"], ["infographic-1.png", "infographic-2.png"])
        self.assertEqual(after["poster_page_groups"][0]["start_page_index"], 1)
        self.assertEqual(after["poster_page_groups"][-1]["end_page_index"], len(after["script"]) - 1)
        self.assertTrue(publish_gate.image_manifest_shape_valid(after, after["image_assets"]))
        self.assertFalse(publish_gate.image_manifest_shape_valid(after, after["image_assets"][:1]))

    def test_prompts_render_three_finished_posters(self):
        story = story_engine.build_story(example_payload("2026-10-15"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "story.json"
            path.write_text(json.dumps(story, ensure_ascii=False))
            _, prompts = image_generator.story_prompts(path)
        self.assertEqual(len(prompts), 3)
        self.assertIn("opening-thumbnail.png", prompts)
        for name in ("infographic-1.png", "infographic-2.png"):
            self.assertIn("finished premium vertical Japanese AI-news editorial infographic", prompts[name])
            self.assertIn("Exact main headline", prompts[name])
            self.assertIn("spoken subtitles", prompts[name])

    def test_renderer_holds_opening_and_uses_narration_page_groups(self):
        source = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertIn("OPENING_HOLD_END", source)
        self.assertIn('story["poster_page_groups"]', source)
        self.assertIn("add_timed_subtitles(events, cue)", source)


if __name__ == "__main__":
    unittest.main()
