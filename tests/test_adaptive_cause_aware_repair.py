import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import self_heal_adaptive_daily_video as recovery  # noqa: E402


class AdaptiveCauseAwareRepairTest(unittest.TestCase):
    def test_same_input_same_failure_stops_generic_full_rerender(self):
        result = {
            "success": False,
            "qa": {"decode_error_free": False, "headline_layout_qa": True},
            "publish_blockers": ["qa:decode_error_free"],
        }
        signature = recovery.failure_signature(result)
        self.assertTrue(
            recovery.should_stop_same_input_failure(
                result,
                previous_signature=signature,
                same_inputs=True,
                regenerated=False,
            )
        )

    def test_changed_images_allow_one_new_render(self):
        result = {
            "success": False,
            "qa": {"decode_error_free": False},
            "publish_blockers": ["qa:decode_error_free"],
        }
        signature = recovery.failure_signature(result)
        self.assertFalse(
            recovery.should_stop_same_input_failure(
                result,
                previous_signature=signature,
                same_inputs=True,
                regenerated=True,
            )
        )

    def test_headline_only_failure_uses_targeted_repair_instead_of_stop(self):
        result = {
            "success": False,
            "qa": {"headline_layout_qa": False},
            "publish_blockers": ["qa:headline_layout_qa"],
        }
        signature = recovery.failure_signature(result)
        self.assertFalse(
            recovery.should_stop_same_input_failure(
                result,
                previous_signature=signature,
                same_inputs=True,
                regenerated=False,
            )
        )
        self.assertTrue(
            recovery.can_apply_opening_only_fix(
                result,
                video_exists=True,
                thumbnail_exists=True,
                regenerated=False,
            )
        )

    def test_opening_only_fix_requires_existing_media_and_unchanged_images(self):
        result = {"qa": {"headline_layout_qa": False}}
        self.assertFalse(
            recovery.can_apply_opening_only_fix(
                result,
                video_exists=False,
                thumbnail_exists=True,
                regenerated=False,
            )
        )
        self.assertFalse(
            recovery.can_apply_opening_only_fix(
                result,
                video_exists=True,
                thumbnail_exists=True,
                regenerated=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
