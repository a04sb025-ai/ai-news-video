import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("adaptive_daily_story", ROOT / "scripts/adaptive_daily_story.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def page(role, headline, narration):
    return {
        "page_role": role,
        "headline": headline,
        "support_text": "初心者にも位置づけが分かるように説明する",
        "narration": narration,
        "subtitle": narration,
        "visual_intent": "モデル規模の違いと位置づけを具体的な比較で示す",
        "key_visuals": ["小型モデル", "30B級", "大型モデル"],
        "mozo_line": "ここがポイント",
        "mozo_usage": "比較の中央を指す",
    }


class AdaptiveExplainerTest(unittest.TestCase):
    def payload(self):
        pages = [
            page("hook", "いま30B級が注目される理由", "いま30B級のAIモデルが相次いで登場し、注目を集めています。"),
            page("landscape", "AIモデルには幅がある", "AIモデルには小さなものから非常に大きなものまで、さまざまな規模があります。"),
            page("definition", "30Bは300億個", "30BのBはビリオンで、約300億個のパラメータを持つ規模を表します。"),
            page("position", "30B級は中間の選択肢", "30B級は巨大モデルほど重くなく、小型モデルより性能を狙いやすい位置づけです。"),
            page("conclusion", "性能と扱いやすさの両立", "だから30B級は、性能と扱いやすさのバランスを狙う選択肢として注目されています。"),
        ]
        return {
            "request_id": "daily-news-test",
            "source_url": "https://example.com/source",
            "article_url": "https://aitoolwatch.jp/news/",
            "headline": pages[0]["headline"],
            "hook": pages[0]["narration"],
            "summary": pages[1]["narration"],
            "points": [pages[3]["headline"], pages[-1]["headline"]],
            "pages": pages,
            "narration_terms": {"30B": "サーティービー"},
        }

    def test_variable_pages_and_duration_are_supported(self):
        payload = module.validate(self.payload())
        story = module.build_story(payload)
        self.assertEqual(story["explanation_contract"], "adaptive-pages-v1")
        self.assertEqual(story["adaptive_page_count"], 5)
        self.assertEqual(len(story["script"]), 6)  # 5 explanation pages + outro
        self.assertGreater(story["expected_duration_seconds"], 25)
        self.assertEqual(len(story["image_assets"]), 4)

    def test_opening_headline_is_physically_narrow(self):
        story = module.build_story(module.validate(self.payload()))
        lines = story["script"][0]["caption"].splitlines()
        self.assertLessEqual(len(lines), 2)
        self.assertTrue(all(len(line) <= 9 for line in lines))
        self.assertEqual("".join(lines), self.payload()["pages"][0]["headline"])

    def test_renderer_uses_large_mobile_subtitles(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertIn("Style: Subtitle,Noto Sans CJK JP,52", renderer)
        self.assertIn("Style: OpeningSubtitle,Noto Sans CJK JP,46", renderer)
        self.assertIn('"opening_headline_target_chars_per_line": 9', renderer)


if __name__ == "__main__":
    unittest.main()
