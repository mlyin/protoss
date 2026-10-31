# Decisions

- 2026-10-31: Dev process runs on harness/ (check.sh GREEN, feedback with dead ends, gates by undo cost, rooms per task). CI runs the same check on PRs.
- 2026-10-31: Ad headline is 'Your friends. One wall.'; brand files live in brand/, posters also on the 'Coliseum Ads' Design canvas.
- 2026-10-31: Shared brain lives in brain/ (LLM-wiki pattern); CLAUDE.md and AGENTS.md point every agent at it. Corrections go in corrections.md, one line, dated.
- 2026-10-31: Rebrand Koinon -> **Coliseum**; pooled org -> **phalanx**. Design motto: black-and-white comic Spartans. (Matthew)
- 2026-10-31: Add a social layer (profiles, follows, derived feed, phalanx pages with invite + deposit) and the Lab
  (plain-English backtesting chat). Anyone can open a phalanx in sim/paper; testnet needs the admin API until wallet auth.
- 2026-10-31: First host is a Mac mini with launchd + Tailscale Funnel; Render/Fly later once the GitHub repo exists.
- 2026-10-31: Database is Supabase Postgres (project `koinon`). SQLite stays for local demos.
- 2026-10-31: Builder code = a dedicated wallet, not Matthew's personal account (public address, company revenue,
  must stay in standard mode). Fee 0.03%.
- 2026-10-31: We do not install or operate VPNs to get around Hyperliquid's jurisdiction block, and we need an
  entity / eligibility answer for the US-person question before the Imran call.
- 2026-10-30: Build the "agent exchange layer" idea (risk-sandboxed hosted execution + SDK + public leaderboard,
  builder-code revenue) rather than cross-venue portfolio margin, which overlaps an existing company Matthew spoke with.
- 2026-10-30: FastAPI >= 0.118 runs yield-dependency teardown after the response; DB sessions use a function-scoped
  dependency (`DbDep`) so commits land before the next request. Lost-update bug found in pool accounting.
