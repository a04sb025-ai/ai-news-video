#!/usr/bin/env bash
# Run opening QA and exactly one deterministic layout-only correction.
set -uo pipefail
VIDEO=$1
STORY=$2
REPORT_DIR=$3
mkdir -p "$REPORT_DIR"
set +e
python3 scripts/check_opening_frames.py "$VIDEO" "$STORY" "$REPORT_DIR" | tee "$REPORT_DIR/../opening-qa.txt"
status=${PIPESTATUS[0]}
set -e
if [[ "$status" -eq 0 ]]; then
  exit 0
fi
echo "Opening QA failed; rendering one safe correction pass" | tee -a "$REPORT_DIR/../opening-qa.txt"
renderer="scripts/render_reference.py"
if python3 - "$STORY" <<'PY'
import json, sys
story=json.load(open(sys.argv[1]))
raise SystemExit(0 if story.get("explanation_contract") == "four-page-v1" else 1)
PY
then
  renderer="scripts/render_explainer.py"
elif python3 - "$STORY" <<'PY'
import json, sys
story=json.load(open(sys.argv[1]))
raise SystemExit(0 if story.get("explanation_contract") == "adaptive-pages-v1" else 1)
PY
then
  renderer="scripts/render_adaptive_explainer.py"
fi
OPENING_SAFE_MODE=1 python3 "$renderer" "$STORY" "$VIDEO"
python3 scripts/check_opening_frames.py "$VIDEO" "$STORY" "$REPORT_DIR" | tee -a "$REPORT_DIR/../opening-qa.txt"
