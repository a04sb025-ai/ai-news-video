import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("self_heal", ROOT / "scripts/self_heal_daily_video.py")
self_heal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(self_heal)


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


if __name__ == "__main__":
    unittest.main()
