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
        self.assertIn("Style: Subtitle,Noto Sans CJK JP,48", renderer)
        self.assertIn("Style: OpeningSubtitle,Noto Sans CJK JP,46", renderer)
        self.assertIn('"opening_headline_target_chars_per_line": 9', renderer)
        self.assertIn('"subtitle_font_size_px": 48', renderer)

    def test_adaptive_renderer_uses_single_pass_audio_led_timing(self):
        renderer = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        self.assertIn("OPEN_JTALK_RATE = 1.10", renderer)
        self.assertIn("FINAL_END_PAUSE_SECONDS = 0.18", renderer)
        self.assertIn('narration.write_text(" ".join(cue["narration"].strip() for cue in story["script"])', renderer)
        self.assertNotIn('narration.write_text("\\n".join(cue["narration"].strip() for cue in story["script"])', renderer)
        self.assertIn('narration_wav = tmp / "voice-single-pass.wav"', renderer)
        self.assertIn('DURATION = round(narration_duration + FINAL_END_PAUSE_SECONDS, 4)', renderer)
        self.assertIn('"audio_pipeline": "single-pass-open-jtalk-audio-led-v2"', renderer)
        self.assertIn('"audio_single_pass": True', renderer)
        self.assertIn('"audio_alignment_source": "probe-duration-proportional"', renderer)
        self.assertIn('"audio_tempo_adjustment": False', renderer)
        self.assertNotIn("cue_wavs.append", renderer)
        self.assertNotIn("concat=n={len(cue_wavs)}", renderer)
        self.assertNotIn("atempo=", renderer)

    def test_reference_renderer_keeps_fixed_speed_audio_led_timing(self):
        renderer = (ROOT / "scripts/render_reference.py").read_text()
        self.assertIn("OPEN_JTALK_RATE = 1.10", renderer)
        self.assertIn("SCENE_END_PAUSE_SECONDS = 0.18", renderer)
        self.assertIn('cue["start"] = start', renderer)
        self.assertIn('cue["end"] = end', renderer)
        self.assertIn("cue_wavs.append(raw_wav)", renderer)
        self.assertIn("story_path.write_text", renderer)
        self.assertIn('"audio_pipeline": "fixed-rate-open-jtalk-audio-led-v1"', renderer)
        self.assertIn('"audio_tempo_adjustment": False', renderer)
        self.assertNotIn("atempo=", renderer)

    def test_rendered_timing_metadata_and_images_follow_measured_audio(self):
        adaptive = (ROOT / "scripts/render_adaptive_explainer.py").read_text()
        reference = (ROOT / "scripts/render_reference.py").read_text()
        self.assertIn('story["expected_duration_seconds"] = round(DURATION, 2)', adaptive)
        self.assertIn('image_cues = story["script"][:len(STORY_IMAGES)]', reference)
        self.assertIn('start, end = float(cue["start"]), float(cue["end"])', reference)
        self.assertNotIn("((0, 3), (3, 6), (6, 9), (9, 12))", reference)
        self.assertNotIn("overlay=enable='between(t,0,3)'", reference)

    def test_explicit_pronunciation_terms_remain_authoritative(self):
        self.assertEqual(module.speak("30B級です", {"30B": "サーティービー"}), "サーティービー級です")

    def test_common_english_names_are_normalized_before_tts(self):
        spoken = module.speak("OpenAIとMicrosoftをSeattle Timesが提訴", {})
        self.assertEqual(spoken, "オープンエーアイとマイクロソフトをシアトル タイムズが提訴")
        self.assertIsNone(module.LATIN_TOKEN.search(spoken))

    def test_unknown_ascii_tokens_fall_back_to_deterministic_letter_reading(self):
        spoken = module.speak("ABC-X9を試す", {})
        self.assertNotIn("ABC", spoken)
        self.assertNotIn("X9", spoken)
        self.assertIsNone(module.LATIN_TOKEN.search(spoken))


if __name__ == "__main__":
    unittest.main()
