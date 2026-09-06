import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OpeningCorrectionRendererTest(unittest.TestCase):
    def run_wrapper(self, contract, first=1, final=0, render=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            story = root / "story with spaces.json"
            story.write_text(json.dumps({"explanation_contract": contract}))
            fake = root / "python3"
            fake.write_text('''#!/bin/bash
if [[ "$1" == "-" ]]; then exec "$REAL_PYTHON" "$@"; fi
if [[ "$1" == *check_opening_frames.py ]]; then
  if [[ -f "$STATE" ]]; then exit "$FINAL_QA"; fi
  touch "$STATE"
  exit "$FIRST_QA"
fi
printf '%s\\n' "$1" "$2" "$3" "$OPENING_SAFE_MODE" > "$RENDER_CALL"
exit "$RENDER_STATUS"
''')
            fake.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       REAL_PYTHON=sys.executable, STATE=str(root / "state"),
                       RENDER_CALL=str(root / "render-call"), FIRST_QA=str(first),
                       FINAL_QA=str(final), RENDER_STATUS=str(render))
            video = root / "video with spaces.mp4"
            result = subprocess.run([
                "bash", str(ROOT / "scripts/opening_qa_with_correction.sh"),
                str(video), str(story), str(root / "reports/opening"),
            ], env=env, cwd=ROOT, capture_output=True, text=True)
            call = root / "render-call"
            args = call.read_text().splitlines() if call.exists() else []
            if args:
                self.assertEqual(args[1:], [str(story), str(video), "1"])
            return result.returncode, args

    def test_adaptive_correction_keeps_adaptive_renderer(self):
        status, args = self.run_wrapper("adaptive-pages-v1")
        self.assertEqual(status, 0)
        self.assertEqual(args[0], "scripts/render_adaptive_explainer.py")

    def test_four_page_correction_keeps_four_page_renderer(self):
        status, args = self.run_wrapper("four-page-v1")
        self.assertEqual((status, args[0]), (0, "scripts/render_explainer.py"))

    def test_legacy_correction_keeps_reference_renderer(self):
        status, args = self.run_wrapper(None)
        self.assertEqual((status, args[0]), (0, "scripts/render_reference.py"))

    def test_passed_opening_does_not_render(self):
        self.assertEqual(self.run_wrapper("adaptive-pages-v1", first=0), (0, []))

    def test_failed_final_qa_remains_failure(self):
        status, _ = self.run_wrapper("adaptive-pages-v1", final=1)
        self.assertEqual(status, 1)

    def test_failed_render_remains_failure(self):
        status, _ = self.run_wrapper("adaptive-pages-v1", render=7)
        self.assertEqual(status, 7)


if __name__ == "__main__":
    unittest.main()
