#!/usr/bin/env bash
# What GREEN means for this repo. Level 3 of the ladder: a check that can fail, run before anyone says "done".
#
#   harness/check.sh                      # full check in this tree
#   harness/check.sh --fence "backend/app/lab.py backend/tests/test_lab.py"   # also fail if the diff leaves the fence
#   harness/check.sh --base origin/master # diff against another ref (default: HEAD)
#
# Each check prints one line:  CHECK <name> ok | CHECK <name> FAIL  EXPECTED <...>  SAW <...>
# Exit 0 only when every check passed. Output is machine-readable on purpose (harness/feedback.py parses it).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FENCE=""; BASE="HEAD"; FAILS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --fence) FENCE="$2"; shift 2 ;;
    --base) BASE="$2"; shift 2 ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done
PY="${PYTHON:-python3}"; [ -x "$ROOT/.venv/bin/python" ] && PY="$ROOT/.venv/bin/python"

ok()   { echo "CHECK $1 ok"; }
fail() { echo "CHECK $1 FAIL  EXPECTED $2  SAW $3"; FAILS=$((FAILS+1)); }

# 1. tests (deterministic, strongest evidence)
out="$(cd backend && "$PY" -m pytest -q -p no:cacheprovider 2>&1)"; rc=$?
if [ $rc -eq 0 ]; then ok "tests ($(echo "$out" | tail -1 | tr -d '\n'))"
else fail tests "pytest exit 0" "$(echo "$out" | grep -E '^(FAILED|ERROR)' | head -5 | tr '\n' ';')"; echo "$out" | grep -E '^E ' | head -20 | sed 's/^/  /'; fi

# 2. the Postgres path, when a local Postgres is reachable (same suite, fresh schema per test)
if [ -n "${TEST_DATABASE_URL:-}" ]; then
  out="$(cd backend && TEST_DATABASE_URL="$TEST_DATABASE_URL" "$PY" -m pytest -q -p no:cacheprovider 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then ok "tests-postgres"; else fail tests-postgres "pytest exit 0 on Postgres" "$(echo "$out" | grep -E '^(FAILED|ERROR)' | head -3 | tr '\n' ';')"; fi
fi

# 3. the web app compiles (only when its sources changed or dist is missing)
if [ ! -d web/dist ] || ! git diff --quiet "$BASE" -- web/src web/index.html 2>/dev/null; then
  if [ -d web/node_modules ]; then
    out="$(cd web && npm run build 2>&1)"; rc=$?
    if [ $rc -eq 0 ]; then ok "web-build"; else fail web-build "vite build exit 0" "$(echo "$out" | grep -iE 'error' | head -3 | tr '\n' ';')"; fi
  else ok "web-build (skipped: no node_modules)"; fi
else ok "web-build (unchanged)"; fi

# 4. no secrets in tracked files
if git ls-files -z | xargs -0 grep -lE '(ar_(owner|live|org)_[A-Za-z0-9_-]{8,}|HL_MASTER_PRIVATE_KEY=0x[0-9a-fA-F]{20,}|"private_key": *"[0-9a-fA-F]{40,}|sb_secret_|postgres(ql)?(\+psycopg)?://[^:]+:[^@<]{8,}@)' 2>/dev/null | grep -vqE '^(harness/check.sh)$'; then
  fail secrets "no keys or connection strings in tracked files" "$(git ls-files -z | xargs -0 grep -lE '(ar_(owner|live|org)_[A-Za-z0-9_-]{8,}|HL_MASTER_PRIVATE_KEY=0x[0-9a-fA-F]{20,}|\"private_key\": *\"[0-9a-fA-F]{40,}|sb_secret_|postgres(ql)?(\+psycopg)?://[^:]+:[^@<]{8,}@)' 2>/dev/null | grep -vE '^(harness/check.sh)$' | tr '\n' ' ')"
else ok secrets; fi

# 5. copy follows brain/voice.md in the places people read (UI strings, brand, README, brain)
banned='excited to announce|thrilled|game-changer|game changing|revolutioniz|seamless|supercharge|delve|in today.s|the future of|AI-powered|genuinely|honestly'
hits="$(grep -rniE "($banned)" web/src brand/*.md README.md brain 2>/dev/null | grep -viE 'voice.md|banned|no hype|never the words|R1\.|swipe.md.*avoid|harness/' | head -5)"
if [ -n "$hits" ]; then fail voice "no banned words in copy (brain/voice.md)" "$(echo "$hits" | cut -c1-120 | tr '\n' ';')"; else ok voice; fi
# the lone quoted '—' is the empty-value glyph in tables, not prose; everything else is a dash in copy
dashes="$(grep -rn "—" web/src brand/copy.md brand/x-thread.md 2>/dev/null | grep -v "x-thread.md:.*R3" | grep -vE "'—'" | head -3)"
if [ -n "$dashes" ]; then
  fail em-dash "no em dashes in UI or brand copy" "$(echo "$dashes" | cut -c1-100 | tr '\n' ';')"
else ok em-dash; fi

# 6. the fence: a task may only touch what it was given (Level 4 FENCE, enforced not requested)
if [ -n "$FENCE" ]; then
  changed="$(git diff --name-only "$BASE" 2>/dev/null; git ls-files --others --exclude-standard)"
  outside=""
  for f in $changed; do
    case "$f" in PROGRESS.md|web/node_modules|.venv|harness/runs/*) continue ;; esac   # the harness's own files
    inside=0
    for p in $FENCE; do case "$f" in $p|$p/*) inside=1 ;; esac; done
    [ $inside -eq 0 ] && outside="$outside $f"
  done
  if [ -n "$outside" ]; then fail fence "changes only under: $FENCE" "touched:$outside"; else ok fence; fi
fi

# 7. walls: paths no agent may change without a person (harness/graph.yaml no_undo list)
walls="$("$PY" - <<'EOF'
import yaml, pathlib
g = yaml.safe_load(pathlib.Path("harness/graph.yaml").read_text())
print(" ".join(g["gates"]["no_undo"]["paths"]))
EOF
)"
touched_walls=""
for f in $(git diff --name-only "$BASE" 2>/dev/null); do
  for p in $walls; do case "$f" in $p|$p/*) touched_walls="$touched_walls $f" ;; esac; done
done
if [ -n "$touched_walls" ]; then echo "CHECK walls NOTE  these paths need a person's sign-off before merge:$touched_walls"; else ok walls; fi

echo "RESULT $([ $FAILS -eq 0 ] && echo GREEN || echo RED) fails=$FAILS"
[ $FAILS -eq 0 ]
