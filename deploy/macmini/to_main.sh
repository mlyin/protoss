#!/usr/bin/env bash
# On the Mac mini: save the running checkout's uncommitted work to its own branch, push it, then run main.
#
#   bash ~/protoss/deploy/macmini/to_main.sh            # do it
#   bash ~/protoss/deploy/macmini/to_main.sh --dry-run  # show what would be saved, change nothing
#
# Refuses to commit anything that looks like a key or local secret (.env, wallets.json, *.pem, ...); those stay on disk,
# untracked. After switching it runs bootstrap.sh, which pulls, rebuilds the dashboard and reloads the launchd services.
set -euo pipefail
DIR="${PROTOSS_DIR:-$HOME/protoss}"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
cd "$DIR"
say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

if [ -n "$(git status --porcelain)" ]; then
  branch="mini/wip-$(date +%Y%m%d-%H%M)"
  say "Uncommitted work on $(git branch --show-current) (it goes to $branch):"
  git status --short | sed 's/^/    /'
  secret='(^|/)\.env($|\.)|wallets\.json|\.fleet-keys|\.builder-wallet|\.pem$|\.key$|telegram\.env'
  if git status --porcelain --untracked-files=all | awk '{print $NF}' | grep -Eq "$secret"; then
    say "These look like secrets and will NOT be committed:"
    git status --porcelain --untracked-files=all | awk '{print $NF}' | grep -E "$secret" | sed 's/^/    /'
  fi
  [ "$DRY" = 1 ] && { say "Dry run: nothing changed."; exit 0; }
  git switch -c "$branch"
  git add -A
  git status --porcelain --untracked-files=all | awk '{print $NF}' | grep -E "$secret" | xargs -r git reset -q --
  git commit -q -m "mini: save the running checkout's uncommitted work before switching to main"
  git push -q -u origin "$branch"
  say "Saved and pushed $branch."
else
  say "No uncommitted work on $(git branch --show-current)."
  [ "$DRY" = 1 ] && { say "Dry run: nothing changed."; exit 0; }
fi

git fetch -q origin
git switch -q main 2>/dev/null || git switch -q -c main --track origin/main
git pull -q --ff-only
say "Now on main at $(git log --oneline -1)."
[ -n "${PROTOSS_SKIP_BOOTSTRAP:-}" ] && { say "Skipping bootstrap (PROTOSS_SKIP_BOOTSTRAP set)."; exit 0; }
bash deploy/macmini/bootstrap.sh
say "Done. Check: deploy/macmini/protossctl status"
