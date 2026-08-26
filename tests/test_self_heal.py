import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("self_heal", SCRIPTS / "self_heal_daily_video.py")
self_heal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(self_heal)

adaptive_spec = importlib.util.spec_from_file_location(
    "self_heal_adaptive", SCRIPTS / "self_heal_adaptive_daily_video.py"
)
self_heal_adaptive = importlib.util.module_from_spec(adaptive_spec)
adaptive_spec.loader.exec_module(self_heal_adaptive)

automation_spec = importlib.util.spec_from_file_location(
    "write_automation_result", SCRIPTS / "write_automation_result.py"
)
automation_result = importlib.util.module_from_spec(automation_spec)
automation_spec.loader.exec_module(automation_result)


class SelfHealPolicyTest(unittest.TestCase):
    def test_semantic_headline_mismatch_is_never_auto_repaired(self):
        result = {
            "qa": {"story_validation": True, "voice_script_qa": True},
            "qa_details": {"headline_layout_qa": {"reason": "headline_matches_verified_story"}},
        }
        self.assertTrue(self_heal.is_semantic_stop(result))

    def test_visual_or_media_failure_remains_repairable(self):
        result = {
            "qa": {"story_validation": True, "voice_script_qa": True, "black_frame_check": False},
            "qa_details": {"headline_layout_qa": {"reason": "frame_0s_headline_visible"}},
        }
        self.assertFalse(self_heal.is_semantic_stop(result))

    def test_missing_video_does_not_trigger_size_transcode(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(self_heal.optimize_if_needed(Path(directory) / "missing.mp4"))

    def test_default_repair_budget_is_bounded(self):
        self.assertGreaterEqual(self_heal.MAX_REPAIRS, 0)
        self.assertLessEqual(self_heal.MAX_REPAIRS, 3)

    def test_adaptive_all_scene_manifest_accepts_variable_page_count(self):
        story = {
            "all_scene_visuals_required": True,
            "adaptive_page_count": 8,
            "image_scenes": [{} for _ in range(8)],
        }
        expected = [f"scene-{index}.png" for index in range(1, 9)]
        self.assertTrue(automation_result.image_manifest_shape_valid(story, expected))

    def test_adaptive_all_scene_manifest_rejects_missing_image(self):
        story = {
            "all_scene_visuals_required": True,
            "adaptive_page_count": 8,
            "image_scenes": [{} for _ in range(8)],
        }
        expected = [f"scene-{index}.png" for index in range(1, 8)]
        self.assertFalse(automation_result.image_manifest_shape_valid(story, expected))

    def test_legacy_manifest_still_requires_four_images(self):
        self.assertTrue(automation_result.image_manifest_shape_valid({}, ["a", "b", "c", "d"]))
        self.assertFalse(automation_result.image_manifest_shape_valid({}, ["a", "b", "c", "d", "e"]))

    def test_publish_only_manual_gate_does_not_rerender(self):
        result = {
            "success": True,
            "auto_publish_ready": False,
            "qa": {"video_qa": True, "voice_script_qa": True},
            "publish_blockers": ["manual_visual_review_required"],
        }
        self.assertFalse(self_heal_adaptive.publish_only_retryable(result, [], True))

    def test_generated_image_blocker_gets_only_one_successful_regeneration(self):
        result = {
            "success": True,
            "auto_publish_ready": False,
            "qa": {"video_qa": True, "voice_script_qa": True},
            "publish_blockers": ["generated_images_not_ready"],
        }
        self.assertTrue(self_heal_adaptive.publish_only_retryable(result, [], True))
        attempts = [{
            "action": "safe-rerender",
            "regenerated_images": True,
            "publish_blockers": ["generated_images_not_ready"],
        }]
        self.assertFalse(self_heal_adaptive.publish_only_retryable(result, attempts, True))

    def test_generated_image_blocker_without_key_does_not_rerender(self):
        result = {
            "success": True,
            "auto_publish_ready": False,
            "qa": {"video_qa": True, "voice_script_qa": True},
            "publish_blockers": ["generated_images_not_ready"],
        }
        self.assertFalse(self_heal_adaptive.publish_only_retryable(result, [], False))


if __name__ == "__main__":
    unittest.main()
