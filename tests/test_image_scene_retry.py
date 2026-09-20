"""Offline regression tests for partial image failures and image-only recovery."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("scene_generator", ROOT / "scripts/generate_story_images.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
import self_heal_adaptive_daily_video as adaptive  # noqa: E402


class ImageSceneRetryTest(unittest.TestCase):
    def test_safety_rejection_recovers_only_missing_scene_serially(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            prompts = {f"scene-{n}.png": f"Verified context {n}" for n in range(1, 4)}
            calls = Counter()

            def fake_generate(destination, prompt, key, quality):
                calls[destination.name] += 1
                if destination.name == "scene-2.png" and calls[destination.name] == 1:
                    raise generator.ImageGenerationError(
                        "safety rejection", status=400, provider_error="rejected by safety system",
                        request_id="req-test-scene-2",
                    )
                destination.write_bytes(b"valid image")
                return {"result": "generated", "attempts": 1}

            report = {}
            with patch.object(generator, "generate", side_effect=fake_generate), patch.object(generator, "FAILED_SCENE_RETRIES", 1):
                passed = generator.generate_pending_scenes(output, prompts, "not-a-real-key", "low", report)
            self.assertTrue(passed)
            self.assertEqual(calls, Counter({"scene-1.png": 1, "scene-2.png": 2, "scene-3.png": 1}))
            self.assertEqual(report["initial_failed_scenes"], ["scene-2.png"])
            self.assertEqual(report["failures"], [])
            self.assertEqual(report["status"], "complete")
            self.assertEqual(len(report["images"]), 3)
            self.assertTrue(all((output / name).exists() for name in prompts))

    def test_persistent_rejection_records_exact_scene_and_keeps_publish_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            prompts = {"scene-4.png": "Verified news text for scene four"}
            calls = Counter()

            def refused(destination, prompt, key, quality):
                calls[destination.name] += 1
                raise generator.ImageGenerationError(
                    "safety rejection", status=400, provider_error="rejected by safety system",
                    request_id="req-test-rejected",
                )

            report = {}
            with patch.object(generator, "generate", side_effect=refused), patch.object(generator, "FAILED_SCENE_RETRIES", 1):
                passed = generator.generate_pending_scenes(output, prompts, "not-a-real-key", "low", report)
            self.assertFalse(passed)
            self.assertEqual(calls["scene-4.png"], 2)
            self.assertEqual(report["images"], [])
            self.assertEqual(report["status"], "partial-failure")
            failure = report["failures"][0]
            self.assertEqual(failure["file"], "scene-4.png")
            self.assertEqual(failure["status"], 400)
            self.assertEqual(failure["request_id"], "req-test-rejected")
            self.assertEqual(failure["prompt"], prompts["scene-4.png"])
            self.assertTrue(failure["serial_retry"])

    def test_auth_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = Counter()

            def unauthorized(destination, prompt, key, quality):
                calls[destination.name] += 1
                raise generator.ImageGenerationError("invalid key", status=401)

            report = {}
            with patch.object(generator, "generate", side_effect=unauthorized), patch.object(generator, "FAILED_SCENE_RETRIES", 1):
                passed = generator.generate_pending_scenes(
                    Path(directory), {"scene-4.png": "verified"}, "invalid", "low", report
                )
            self.assertFalse(passed)
            self.assertEqual(calls["scene-4.png"], 1)


class AdaptiveImageOnlyRecoveryTest(unittest.TestCase):
    def test_failed_image_retry_never_rebuilds_same_video(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            story = root / "story.json"
            story.write_text("{}")
            video = root / "video.mp4"
            video.write_bytes(b"original render")
            result = {
                "success": True, "auto_publish_ready": False, "used_generated_images": False,
                "qa": {"story_validation": True, "voice_script_qa": True, "video_qa": True},
                "publish_blockers": ["generated_images_not_ready"],
            }
            (root / "automation-result.json").write_text(json.dumps(result))
            with (patch.object(sys, "argv", ["heal", str(story), str(video), str(root)]),
                  patch.object(adaptive, "MAX_REPAIRS", 2),
                  patch.dict(os.environ, {"OPENAI_API_KEY": "not-a-real-key"}),
                  patch.object(adaptive.base, "regenerate_images_if_needed", return_value=False) as recover,
                  patch.object(adaptive.base, "archive_attempt"),
                  patch.object(adaptive.base, "run") as render,
                  contextlib.redirect_stdout(io.StringIO())):
                code = adaptive.main()
            summary = json.loads((root / "self-heal-summary.json").read_text())
            self.assertEqual(code, 1)
            self.assertEqual(recover.call_count, 1)
            render.assert_not_called()
            self.assertEqual(video.read_bytes(), b"original render")
            self.assertEqual(summary["repairs"], 0)
            self.assertEqual(summary["attempts"][0]["reason"], "missing-images-after-targeted-retry")
            self.assertEqual(summary["publish_blockers"], ["generated_images_not_ready"])


if __name__ == "__main__":
    unittest.main()
