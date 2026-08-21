#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT"/{vendor,work,dist,reports}
"$ROOT/scripts/openmontage.sh" install
python3 "$ROOT/scripts/doctor.py"
