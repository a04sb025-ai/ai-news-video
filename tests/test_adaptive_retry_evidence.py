import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import self_heal_adaptive_daily_video as heal
import write_automation_result as automation


class AdaptiveRetryEvidenceTest(unittest.TestCase):
    def exercise(self, failure="headline_layout_qa", change_image=False,
                 render_failure=False, ready=False, missing_asset=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.png"
            image.write_bytes(b"original artwork")
            character = root / "character.png"
            character.write_bytes(b"character artwork")
            story = root / "story.json"
            story.write_text(json.dumps({
                "image_asset_dir": str(root), "image_assets": [image.name],
                "opening": {"character_asset": str(character)},
            }))
            if missing_asset:
                character.unlink()
            video = root / "video.mp4"
            thumbnail = root / "video.thumbnail.jpg"
            report = root / "automation-result.json"
            result = {"success": False, "auto_publish_ready": False,
                      "used_generated_images": True,
                      "qa": {"story_validation": True, "voice_script_qa": True,
                             failure: False}}
            report.write_text(json.dumps(result))

            def render(*args, **kwargs):
                if render_failure:
                    return 1
                video.write_bytes(b"rejected video retained")
                thumbnail.write_bytes(b"thumbnail retained")
                return 0

            def qa(*args):
                if change_image:
                    image.write_bytes(image.read_bytes() + b" changed")
                if ready:
                    result.update(success=True, auto_publish_ready=True)
                    result["qa"][failure] = True
                report.write_text(json.dumps(result))
                return result

            with (patch.object(sys, "argv", ["heal", str(story), str(video), str(root)]),
                  patch.object(heal, "MAX_REPAIRS", 2),
                  patch.object(heal.base, "run", side_effect=render) as renders,
                  patch.object(heal.base, "regenerate_images_if_needed", return_value=False),
                  patch.object(heal.base, "optimize_if_needed", return_value=False),
                  patch.object(heal.base, "archive_attempt"),
                  patch.object(heal, "perform_qa", side_effect=qa),
                  contextlib.redirect_stdout(io.StringIO())):
                status = heal.main()
            summary = json.loads((root / "self-heal-summary.json").read_text())
            if not render_failure:
                self.assertEqual(video.read_bytes(), b"rejected video retained")
                self.assertTrue(thumbnail.is_file())
            return status, renders.call_count, summary

    def test_identical_opening_retry_stops_without_publishing_or_deleting_evidence(self):
        status, count, summary = self.exercise()
        self.assertEqual((status, count, summary["repairs"]), (1, 1, 1))
        self.assertEqual(summary["attempts"][-1]["reason"], "unchanged-opening-render-inputs")
        self.assertFalse(summary["final"]["auto_publish_ready"])

    def test_changed_artwork_still_gets_second_render(self):
        status, count, _ = self.exercise(change_image=True)
        self.assertEqual((status, count), (1, 2))

    def test_media_failure_still_gets_second_render(self):
        status, count, _ = self.exercise(failure="decode_error_free")
        self.assertEqual((status, count), (1, 2))

    def test_render_failure_still_gets_second_render(self):
        status, count, _ = self.exercise(render_failure=True)
        self.assertEqual((status, count), (1, 2))

    def test_missing_input_evidence_does_not_suppress_retry(self):
        status, count, _ = self.exercise(missing_asset=True)
        self.assertEqual((status, count), (1, 2))

    def test_successful_repair_remains_publishable(self):
        status, count, summary = self.exercise(ready=True)
        self.assertEqual((status, count), (0, 1))
        self.assertTrue(summary["final"]["auto_publish_ready"])

    def test_opening_measurements_are_reported_without_changing_publish_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "opening").mkdir()
            video = root / "video.mp4"
            video.write_bytes(b"fixture")
            (root / "qa.txt").write_text("PASS\n")
            (root / "voice-script-qa.json").write_text('{"passed":true}')
            (root / "video-qa.json").write_text(json.dumps({
                "decode_error_free": {"passed": True}, "black_frame_check": {"passed": True},
            }))
            frames = [{"time": t, "mean_luma": 240, "near_black_ratio": 0.01,
                       "luma_contrast": 30, "regions": {}} for t in [0, 1, 2, 2.967]]
            for passed in [False, True]:
                with self.subTest(passed=passed):
                    (root / "opening/opening-qa.json").write_text(json.dumps({
                        "passed": passed, "checks": {"frame_0s_visible": passed},
                        "reasons": [] if passed else ["frame_0s_visible"], "frames": frames,
                    }))
                    with patch.object(automation, "generated_images_ready", return_value=True):
                        result = automation.build_result({}, video, root)
                    self.assertEqual(result["auto_publish_ready"], passed)
                    details = result["qa_details"]["headline_layout_qa"]
                    self.assertEqual(details["frames"], frames)
                    self.assertEqual(details["failed_checks"], [] if passed else ["frame_0s_visible"])


if __name__ == "__main__":
    unittest.main()
