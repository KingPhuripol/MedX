#!/usr/bin/env bash
# Copy the MedX theme tokens (the only colour source) from web/ into the mobile scribe app (slice v2c).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cp "$root/web/app/theme.css" "$root/mobile/app/theme.css"
echo "synced web/app/theme.css -> mobile/app/theme.css"
