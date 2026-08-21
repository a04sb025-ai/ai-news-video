#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/vendor/openmontage"
URL="https://github.com/calesthio/OpenMontage.git"
action="${1:-install}"
if [[ "$action" == install ]]; then
  [[ -d "$DEST/.git" ]] || git clone --depth 1 "$URL" "$DEST"
elif [[ "$action" == update ]]; then
  [[ -d "$DEST/.git" ]] || { echo "Run scripts/openmontage.sh install first" >&2; exit 2; }
  git -C "$DEST" pull --ff-only
else
  echo "Usage: $0 [install|update]" >&2; exit 2
fi
for doc in README.md CODEX.md AGENT_GUIDE.md PROJECT_CONTEXT.md; do
  [[ -f "$DEST/$doc" ]] || { echo "OpenMontage is missing required $doc" >&2; exit 1; }
done
git -C "$DEST" rev-parse HEAD > "$ROOT/vendor/openmontage.version"
echo "OpenMontage $(cat "$ROOT/vendor/openmontage.version") is ready. Read its four required documents before production."
