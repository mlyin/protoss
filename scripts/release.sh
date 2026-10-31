#!/usr/bin/env bash
# Build a shareable zip of the repo: tracked files + the built dashboard (web/dist), no secrets, no node_modules.
#   scripts/release.sh 0.4 [out_dir]     -> out_dir/coliseum-v0.4.zip and out_dir/coliseum/ (the tree)
set -euo pipefail
VER="${1:?version, e.g. 0.4}"; OUT="${2:-dist-release}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ -d web/dist ] || (cd web && npm run build)
rm -rf "$OUT/coliseum" "$OUT/coliseum-v$VER.zip"; mkdir -p "$OUT/coliseum"
git ls-files -z | xargs -0 -I{} cp --parents {} "$OUT/coliseum/"
mkdir -p "$OUT/coliseum/web" && cp -r web/dist "$OUT/coliseum/web/dist"
(cd "$OUT" && zip -qr "coliseum-v$VER.zip" coliseum)
echo "$OUT/coliseum-v$VER.zip ($(du -h "$OUT/coliseum-v$VER.zip" | cut -f1), $(find "$OUT/coliseum" -type f | wc -l) files)"
