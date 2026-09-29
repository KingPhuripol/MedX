#!/usr/bin/env bash
# Slice d1: assemble a self-contained Vercel deploy dir for the MedX public demo (DECISIONS.md 2026-09-29).
#   <outdir>/            web/ contents (Next.js app at the root, no tests)
#   <outdir>/api/index.py  FastAPI as a Vercel Python function (PUBLIC_DEMO forced)
#   <outdir>/backend/app, casegraph/   runtime Python packages
#   <outdir>/data/synthetic/v1         synthetic inputs + manifest only (no gold labels)
#   <outdir>/requirements.txt, vercel.json, .vercelignore, .python-version
# Usage: scripts/vercel_stage.sh <outdir>   (outdir must be empty, missing, or a previous stage)
set -euo pipefail

OUT="${1:?usage: scripts/vercel_stage.sh <outdir>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="$ROOT/data/synthetic/v1"
MARKER=".medx-vercel-stage"

if [ -e "$OUT" ] && [ -n "$(ls -A "$OUT")" ]; then
  [ -f "$OUT/$MARKER" ] || { echo "refusing: $OUT is not empty and not a previous stage" >&2; exit 2; }
  rm -rf "$OUT"
fi
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
case "$OUT/" in "$ROOT/"*) rmdir "$OUT"; echo "refusing: <outdir> must be outside the repository ($ROOT)" >&2; exit 2 ;; esac

[ -f "$DATA/manifest.json" ] || make -C "$ROOT" data
grep -q '"data_class": *"synthetic"' "$DATA/manifest.json" || { echo "refusing: dataset is not synthetic" >&2; exit 2; }

rsync -a \
  --exclude node_modules --exclude .next --exclude tests --exclude e2e --exclude test-results \
  --exclude playwright-report --exclude next-env.d.ts --exclude '*.tsbuildinfo' \
  --exclude vitest.config.mts --exclude playwright.config.ts \
  "$ROOT/web/" "$OUT/"
mkdir -p "$OUT/backend" "$OUT/data/synthetic/v1"
rsync -a --exclude __pycache__ "$ROOT/backend/app" "$OUT/backend/"
rsync -a --exclude __pycache__ --exclude tests "$ROOT/casegraph" "$OUT/"
rsync -a "$DATA/manifest.json" "$DATA/DATACARD.md" "$DATA/inputs" "$OUT/data/synthetic/v1/"
rsync -a "$ROOT/deploy/vercel/" "$OUT/"
echo "3.12" > "$OUT/.python-version"
printf 'source_rev=%s\nstaged_at=%s\n' "$(git -C "$ROOT" rev-parse HEAD)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$OUT/$MARKER"

echo "staged MedX public demo -> $OUT ($(du -sh "$OUT" | cut -f1))"
