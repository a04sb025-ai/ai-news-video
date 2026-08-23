import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/check_opening_frames.py").read_text()
PREFIX = SOURCE.split("video, story_path, output_dir =", 1)[0]
NAMESPACE = {}
exec(PREFIX, NAMESPACE)
normalize_layout_text = NAMESPACE["normalize_layout_text"]


class OpeningHeadlineNormalizationTest(unittest.TestCase):
    def test_layout_whitespace_is_ignored(self):
        self.assertEqual(
            normalize_layout_text("Claude Academy、正式公開"),
            normalize_layout_text("Claude\nAcademy、正式公開"),
        )
        self.assertEqual(
            normalize_layout_text("Claude\tAcademy、正式公開"),
            normalize_layout_text("Claude Academy、正式公開"),
        )

    def test_semantic_change_still_fails(self):
        self.assertNotEqual(
            normalize_layout_text("Claude Academy、正式公開"),
            normalize_layout_text("Claude Academy、正式開始"),
        )


if __name__ == "__main__":
    unittest.main()
