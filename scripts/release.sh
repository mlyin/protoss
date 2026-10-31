#!/usr/bin/env bash
# Build a shareable zip of the repo: tracked files + the built dashboard (web/dist), no secrets, no node_modules.
#   scripts/release.sh 0.4 [out_dir]     -> out_dir/protoss-v0.4.zip and out_dir/protoss/ (the tree)
set -euo pipefail
VER="${1:?version, e.g. 0.4}"; OUT="${2:-dist-release}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ -d web/dist ] || (cd web && npm run build)
rm -rf "$OUT/protoss" "$OUT/protoss-v$VER.zip"; mkdir -p "$OUT/protoss"
git ls-files -z | xargs -0 -I{} cp --parents {} "$OUT/protoss/"
mkdir -p "$OUT/protoss/web" && cp -r web/dist "$OUT/protoss/web/dist"
(cd "$OUT" && zip -qr "protoss-v$VER.zip" protoss)
echo "$OUT/protoss-v$VER.zip ($(du -h "$OUT/protoss-v$VER.zip" | cut -f1), $(find "$OUT/protoss" -type f | wc -l) files)"
