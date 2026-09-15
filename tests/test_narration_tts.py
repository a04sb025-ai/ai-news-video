import importlib.util
import io
import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("narration_tts", ROOT / "scripts/narration_tts.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def tiny_wav_bytes(sample_rate=24000, duration=0.1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * int(sample_rate * duration))
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


class NarrationTtsTest(unittest.TestCase):
    def test_openai_speech_requests_wav_at_natural_speed(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse(tiny_wav_bytes())

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "speech.wav"
            with mock.patch.object(module.urllib.request, "urlopen", side_effect=fake_urlopen):
                metadata = module.synthesize_openai("自然なニュースです。", output, api_key="test-key")

        payload = json.loads(captured["request"].data.decode("utf-8"))
        self.assertEqual(payload["model"], "gpt-4o-mini-tts-2025-12-15")
        self.assertEqual(payload["voice"], "marin")
        self.assertEqual(payload["response_format"], "wav")
        self.assertEqual(payload["speed"], 1.0)
        self.assertIn("不自然に引き延ば", payload["instructions"])
        self.assertEqual(metadata["provider"], "openai")
        self.assertTrue(metadata["production_preferred"])

    def test_production_key_selects_openai_without_silent_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "speech.wav"
            env = {"OPENAI_API_KEY": "test-key"}
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(module, "synthesize_openai", side_effect=RuntimeError("tts failed")) as openai, \
                 mock.patch.object(module, "synthesize_open_jtalk") as open_jtalk:
                with self.assertRaisesRegex(RuntimeError, "tts failed"):
                    module.synthesize_published_narration(
                        "本文。", output,
                        dictionary=Path("dic"), voice=Path("voice.htsvoice"), open_jtalk_rate=1.10,
                    )
            openai.assert_called_once()
            open_jtalk.assert_not_called()

    def test_offline_ci_uses_open_jtalk_when_no_api_key_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "speech.wav"
            expected = {"provider": "open_jtalk", "duration_seconds": 1.0}
            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch.object(module, "synthesize_open_jtalk", return_value=expected) as fallback:
                actual = module.synthesize_published_narration(
                    "本文。", output,
                    dictionary=Path("dic"), voice=Path("voice.htsvoice"), open_jtalk_rate=1.10,
                )
            self.assertEqual(actual, expected)
            fallback.assert_called_once()

    def test_explicit_openai_requires_key(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "speech.wav"
            with mock.patch.dict(os.environ, {"AI_NEWS_TTS_PROVIDER": "openai"}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "requires OPENAI_API_KEY"):
                    module.synthesize_published_narration(
                        "本文。", output,
                        dictionary=Path("dic"), voice=Path("voice.htsvoice"), open_jtalk_rate=1.10,
                    )


if __name__ == "__main__":
    unittest.main()
