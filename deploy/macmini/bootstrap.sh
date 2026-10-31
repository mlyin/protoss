#!/usr/bin/env bash
# Protoss on a Mac mini from nothing, in one line pasted into Terminal:
#
#   curl -fsSL https://raw.githubusercontent.com/mlyin/protoss/main/deploy/macmini/bootstrap.sh | bash
#
# Clones (or updates) the repo into ~/protoss, builds the dashboard if node is around (installs it with
# Homebrew when it is not), then runs deploy/macmini/install.sh, which sets up the launchd services.
# Re-running is safe: it pulls, rebuilds, reloads. Env: PROTOSS_DIR, PROTOSS_REPO, ARENA_MODE, PORT.
set -euo pipefail

REPO="${PROTOSS_REPO:-https://github.com/mlyin/protoss}"
DIR="${PROTOSS_DIR:-$HOME/protoss}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

if ! xcode-select -p >/dev/null 2>&1; then
  echo "git needs Apple's Command Line Tools. Run:  xcode-select --install   then paste the bootstrap line again." >&2
  exit 1
fi

if [ -d "$DIR/.git" ]; then
  say "Updating $DIR"
  git -C "$DIR" pull --ff-only
else
  say "Cloning $REPO into $DIR"
  git clone --depth 1 "$REPO" "$DIR"
fi
cd "$DIR"

# Dashboard: the API serves web/dist when it exists. Without node the API still runs; the UI just is not served.
if ! command -v npm >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    say "Installing node with Homebrew (for the dashboard build)"
    brew install node
  else
    say "node not found and no Homebrew: skipping the dashboard build (API only). Install Homebrew from https://brew.sh and re-run to get the UI."
  fi
fi
if command -v npm >/dev/null 2>&1; then
  say "Building the dashboard"
  (cd web && npm ci --silent --no-audit --no-fund && npm run build --silent)
fi

bash deploy/macmini/install.sh

echo
say "Next: deploy/macmini/protossctl funnel   gives a public https URL (needs Tailscale with Funnel enabled)."
say "      deploy/macmini/protossctl status   /  logs  /  mode sim|paper|testnet"
