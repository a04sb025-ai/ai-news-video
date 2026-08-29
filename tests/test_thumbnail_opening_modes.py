import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("adaptive_daily_story", ROOT / "scripts/adaptive_daily_story.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
opening_source = (ROOT / "scripts/check_opening_frames.py").read_text()
opening_prefix = opening_source.split("video, story_path, output_dir =", 1)[0]
opening_namespace = {}
exec(opening_prefix, opening_namespace)
scripts_dir = str(ROOT / "scripts")
sys.path.insert(0, scripts_dir)
try:
    RESULT_SPEC = importlib.util.spec_from_file_location("write_adaptive_result", ROOT / "scripts/write_adaptive_result.py")
    adaptive_result = importlib.util.module_from_spec(RESULT_SPEC)
    RESULT_SPEC.loader.exec_module(adaptive_result)
finally:
    sys.path.remove(scripts_dir)


def page(role, headline):
    narration = "ニュースの意味を初心者にも分かるように短く説明します。"
    return {
        "page_role": role,
        "headline": headline,
        "support_text": "初心者向けの短い補足です",
        "narration": narration,
        "subtitle": narration,
        "visual_intent": "ニュースの主役を一つの具体的な場面で見せる",
        "key_visuals": ["主役", "変化"],
        "mozo_line": "ここがポイント",
        "mozo_usage": "主役を邪魔せず補助する",
    }


def payload(style="B"):
    pages = [
        page("hook", "AIが仕事を始める"),
        page("fact", "今回起きたこと"),
        page("impact", "利用者への変化"),
        page("conclusion", "ここが重要"),
    ]
    return {
        "request_id": "thumbnail-style-test",
        "source_url": "https://example.com/source",
        "article_url": "https://aitoolwatch.jp/news/",
        "headline": pages[0]["headline"],
        "hook": pages[0]["narration"],
        "summary": pages[1]["narration"],
        "points": [pages[2]["headline"], pages[3]["headline"]],
        "thumbnail_style": style,
        "pages": pages,
        "narration_terms": {},
    }


class ThumbnailOpeningModesTest(unittest.TestCase):
    def test_thumbnail_style_is_propagated_independently_from_body_template(self):
        for style in ("A", "B", "C"):
            story = module.build_story(module.validate(payload(style)))
            self.assertEqual(story["opening"]["thumbnail_style"], style)
            self.assertFalse(story["opening"]["support_copy_visible"])
            self.assertFalse(story["opening"]["subtitle_visible"])
            self.assertTrue(story["opening"]["single_dominant_visual"])
            self.assertEqual(story["image_scenes"][0]["thumbnail_style"], style)
            self.assertIn(story["visual_template"]["id"], {"A", "B", "C"})

    def test_opening_caption_keeps_event_words_intact(self):
        self.assertEqual(
            module.opening_caption("キオクシア5兆円投資、何が変わる？"),
            "キオクシア5兆円\n投資、何が変わる？",
        )

    def test_invalid_thumbnail_style_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "thumbnail_style must be A, B or C"):
            module.validate(payload("X"))

    def test_missing_style_falls_back_to_magazine_mode_for_legacy_payloads(self):
        legacy = payload()
        legacy.pop("thumbnail_style")
        story = module.build_story(module.validate(legacy))
        self.assertEqual(story["opening"]["thumbnail_style"], "B")

    def test_renderer_keeps_full_copy_out_of_thumbnail_window(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertIn('OPENING_STYLE = story.get("opening", {}).get("thumbnail_style", "B")', renderer)
        self.assertIn('"opening_support_copy_visible": False', renderer)
        self.assertIn('"opening_subtitle_visible": False', renderer)
        self.assertIn('add_opening_body_page(events, cue, OPENING_END, end)', renderer)

    def test_opening_qa_requires_v2_only_for_explicit_thumbnail_contract(self):
        story = module.build_story(module.validate(payload("A")))
        expected = opening_namespace["expected_visual_standard"]
        self.assertEqual(expected(story), "ai-news-visual-v2-thumbnail-abc")
        self.assertEqual(expected({"opening": {}}), "ai-news-visual-v1")
        legacy_with_style_only = {"opening": {"thumbnail_style": "A"}}
        self.assertEqual(expected(legacy_with_style_only), "ai-news-visual-v1")

    def test_adaptive_result_requires_matching_renderer_for_each_contract(self):
        story = module.build_story(module.validate(payload("C")))
        self.assertEqual(adaptive_result.expected_adaptive_renderer(story), "adaptive-explainer-v2-thumbnail-abc")
        self.assertEqual(adaptive_result.expected_adaptive_renderer({"opening": {}}), "adaptive-explainer-v1")
        legacy_with_style_only = {"opening": {"thumbnail_style": "C"}}
        self.assertEqual(adaptive_result.expected_adaptive_renderer(legacy_with_style_only), "adaptive-explainer-v1")


if __name__ == "__main__":
    unittest.main()
