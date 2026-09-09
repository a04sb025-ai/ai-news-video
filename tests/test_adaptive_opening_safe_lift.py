import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import self_heal_adaptive_daily_video as heal


class AdaptiveOpeningSafeLiftTest(unittest.TestCase):
    def test_first_repair_uses_subtle_bounded_lift(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENING_SAFE_VISUAL_LIFT", None)
            self.assertEqual(heal.opening_visual_lift_alpha(1), 0.12)
            self.assertEqual(heal.opening_visual_lift_alpha(2), 0.18)
            self.assertEqual(heal.opening_visual_lift_alpha(9), 0.20)

    def test_lift_override_is_still_bounded(self):
        with patch.dict(os.environ, {"OPENING_SAFE_VISUAL_LIFT": "0.01"}):
            self.assertEqual(heal.opening_visual_lift_alpha(1), 0.06)
        with patch.dict(os.environ, {"OPENING_SAFE_VISUAL_LIFT": "0.50"}):
            self.assertEqual(heal.opening_visual_lift_alpha(1), 0.20)

    def test_video_filter_only_targets_opening_visual_for_first_three_seconds(self):
        value = heal.opening_visual_lift_filter(0.12, timed=True)
        self.assertIn("x=82:y=700:w=916:h=570", value)
        self.assertIn("white@0.12", value)
        self.assertIn("enable='lt(t,3)'", value)

    def test_thumbnail_filter_uses_same_region_without_time_gate(self):
        value = heal.opening_visual_lift_filter(0.12, timed=False)
        self.assertIn("x=82:y=700:w=916:h=570", value)
        self.assertNotIn("enable=", value)


if __name__ == "__main__":
    unittest.main()
