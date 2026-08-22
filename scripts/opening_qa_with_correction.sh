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
OPENING_SAFE_MODE=1 python3 scripts/render_reference.py "$STORY" "$VIDEO"
# With pipefail enabled, a second QA failure is the command's failure.
python3 scripts/check_opening_frames.py "$VIDEO" "$STORY" "$REPORT_DIR" | tee -a "$REPORT_DIR/../opening-qa.txt"
