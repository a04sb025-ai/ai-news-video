import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


daily = load("daily_four_page", "scripts/daily_story.py")
voice = load("voice_four_page", "scripts/check_story_voice.py")
self_heal = load("self_heal_four_page", "scripts/self_heal_daily_video.py")


def rich_payload():
    pages = [
        {
            "page_role": "hook",
            "headline": "著作物をAI学習しても合法？",
            "support_text": "作者の許可なしで使ってよいのか",
            "narration": "著作権のある書籍を、作者の許可なくAI学習に使っていいのでしょうか。",
            "subtitle": "著作権のある書籍を、作者の許可なくAI学習に使っていいのでしょうか。",
            "visual_intent": "本からAI学習へつながる関係を具体的に見せる",
            "key_visuals": ["著作権のある書籍", "AI学習"],
            "mozo_line": "まずここから",
            "mozo_usage": "もぞが本とAIの間を指す",
        },
        {
            "page_role": "fact",
            "headline": "著者は同意なしと指摘",
            "support_text": "通知もないままAI開発に寄与したとされる",
            "narration": "多くの著者は、同意や通知がないまま作品がAI開発に使われたと指摘されています。",
            "subtitle": "多くの著者は、同意や通知がないまま作品がAI開発に使われたと指摘されています。",
            "visual_intent": "著者と書籍、その先のAI開発を具体的に見せる",
            "key_visuals": ["著者", "書籍", "AI開発"],
            "mozo_line": "何が起きた？",
            "mozo_usage": "もぞが著者側を示す",
        },
        {
            "page_role": "issue",
            "headline": "著者の仕事や収入に影響も",
            "support_text": "AIツールが生計を脅かす可能性が懸念される",
            "narration": "著者側は、無断利用だけでなく、AIツールが仕事や収入を脅かす可能性も懸念しています。",
            "subtitle": "著者側は、無断利用だけでなく、AIツールが仕事や収入を脅かす可能性も懸念しています。",
            "visual_intent": "著者の仕事とAIツールの関係を対比する",
            "key_visuals": ["著者の仕事", "AIツール", "収入への影響"],
            "mozo_line": "ここが争点",
            "mozo_usage": "もぞが著者側の懸念を示す",
        },
        {
            "page_role": "conclusion",
            "headline": "合法・違法の線引きは未整理",
            "support_text": "書籍を学習データに使う法的整理が必要",
            "narration": "書籍をAI学習に使うことは一律に合法とも違法とも言えず、法的な整理が必要です。",
            "subtitle": "書籍をAI学習に使うことは一律に合法とも違法とも言えず、法的な整理が必要です。",
            "visual_intent": "書籍とAIの間に法的な線引きが必要な状態を見せる",
            "key_visuals": ["書籍", "AI学習", "法的な線引き"],
            "mozo_line": "結論はここ",
            "mozo_usage": "もぞが両者の境界を指す",
        },
    ]
    return {
        "request_id": "daily-news-2026-08-24-example",
        "news_key": "daily-news-2026-08-24-example",
        "source_url": "https://techcrunch.com/example",
        "article_url": "https://aitoolwatch.jp/news/",
        "headline": pages[0]["headline"],
        "hook": pages[0]["narration"],
        "summary": pages[1]["headline"],
        "points": [pages[2]["headline"], pages[3]["headline"]],
        "pages": pages,
        "narration_terms": {"AI": "エーアイ"},
    }


class FourPageExplainerTest(unittest.TestCase):
    def test_rich_story_has_four_connected_pages_and_full_subtitles(self):
        story = daily.build_story(daily.validate(rich_payload()))
        self.assertEqual(story["explanation_contract"], "four-page-v1")
        self.assertEqual([cue["end"] for cue in story["script"]], [4.5, 9.0, 13.5, 18.0, 19.5])
        self.assertEqual([cue["page_role"] for cue in story["script"][:4]], ["hook", "fact", "issue", "conclusion"])
        for cue in story["script"][:4]:
            self.assertEqual("".join(cue["subtitle"].split()), "".join(cue["source_narration"].split()))
            self.assertTrue(cue["support_text"])
            self.assertTrue(cue["visual_intent"])

    def test_full_narration_subtitle_is_a_publish_gate(self):
        story = daily.build_story(daily.validate(rich_payload()))
        report = voice.build_report(story)
        self.assertTrue(report["checks"]["all_four_pages_have_subtitles"])
        self.assertTrue(report["checks"]["subtitles_cover_full_narration"])
        story["script"][2]["subtitle"] = "短縮字幕"
        self.assertFalse(voice.build_report(story)["checks"]["subtitles_cover_full_narration"])

    def test_rich_image_contract_is_concrete_and_scene_specific(self):
        story = daily.build_story(daily.validate(rich_payload()))
        self.assertEqual(len(story["image_scenes"]), 4)
        self.assertTrue(all(scene.get("visual_intent") for scene in story["image_scenes"]))
        self.assertTrue(all(len(scene.get("key_visuals", [])) >= 2 for scene in story["image_scenes"]))
        generator = (ROOT / "scripts/generate_story_images.py").read_text()
        self.assertIn("meaningless empty boxes", generator)
        self.assertIn("Required concrete visual elements", generator)

    def test_self_heal_selects_explainer_renderer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "story.json"
            path.write_text(json.dumps({"explanation_contract": "four-page-v1"}))
            self.assertEqual(self_heal.renderer_for(path), "scripts/render_explainer.py")
            path.write_text(json.dumps({}))
            self.assertEqual(self_heal.renderer_for(path), "scripts/render_reference.py")

    def test_explainer_renderer_uses_meaningful_support_and_full_subtitles(self):
        source = (ROOT / "scripts/render_explainer.py").read_text()
        self.assertIn('cue["support_text"]', source)
        self.assertIn('cue["subtitle"]', source)
        self.assertNotIn("入力　→　しくみ　→　変化", source)
        self.assertIn('"full_narration_subtitles": True', source)

    def test_opening_contract_remains_three_seconds_even_when_page_one_is_longer(self):
        source = (ROOT / "scripts/check_opening_frames.py").read_text()
        self.assertIn("opening_contract", source)
        story = daily.build_story(daily.validate(rich_payload()))
        self.assertEqual(story["opening"]["end"], 3.0)
        self.assertGreater(story["script"][0]["end"], story["opening"]["end"])


if __name__ == "__main__":
    unittest.main()
