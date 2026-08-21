#!/usr/bin/env bash
# Validate the upstream checkout and install dependencies according to its lockfile.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OM="${OPENMONTAGE_DIR:-$ROOT/vendor/openmontage}"
for doc in README.md CODEX.md AGENT_GUIDE.md PROJECT_CONTEXT.md; do
  test -s "$OM/$doc" || { echo "Missing required OpenMontage document: $doc" >&2; exit 1; }
done
if [[ -f "$OM/pnpm-lock.yaml" ]]; then
  corepack enable
  (cd "$OM" && pnpm install --frozen-lockfile)
elif [[ -f "$OM/yarn.lock" ]]; then
  corepack enable
  (cd "$OM" && yarn install --immutable)
elif [[ -f "$OM/package-lock.json" ]]; then
  (cd "$OM" && npm ci)
elif [[ -f "$OM/package.json" ]]; then
  echo "package.json exists without a lockfile; refusing a non-reproducible install" >&2
  exit 1
else
  echo "No Node dependency manifest found; documentation-only checkout validated."
fi
{
  echo "commit=$(git -C "$OM" rev-parse HEAD)"
  for doc in README.md CODEX.md AGENT_GUIDE.md PROJECT_CONTEXT.md; do sha256sum "$OM/$doc"; done
} | tee "$ROOT/reports/openmontage.txt"

