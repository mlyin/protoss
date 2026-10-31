# Coliseum — instructions for any agent working in this repo

Read `brain/INDEX.md` first, then the brain pages it points to for your task. The brain is the shared
memory for every agent on this project (Claude Code, Codex, Hermes, humans). Before you start work,
pull from it; when you learn something durable (a correction from Matthew, a decision, a runbook step
that changed), write it back, in the right page, dated. One correction should teach the whole team.

Rules that never change:
- Shell and files only on Matthew's machines. Never take over his screen. Never move his money or sign
  with his keys; prepare the command and let him run it.
- Keys never go into chat, commits or the brain. `.env`, `.fleet-keys.json`, `.builder-wallet.json` are gitignored.
- Copy follows `brain/voice.md` (no em dashes, no hype words, numbers over adjectives).
- UI follows `brain/design.md` (ink and paper, one accent, "the line you drew").
- Tests before commits: `cd backend && python -m pytest -q`. Commits end with the attribution trailer the
  session gives you.
- The pooled org is a **phalanx** in product copy; the code says `org`. Do not rename the code.

Quick map: `backend/app` API + sandbox, `sdk/arena` Python SDK, `agents/` example bots, `scripts/` demo,
fleet, builder-code CLI, `deploy/macmini` launchd kit, `web/` dashboard, `brand/` assets and copy, `brain/` memory.
