# Corrections

- 2026-11-01: Matthew asked to shorten episode replies again: default to direction, ticker, and one short reason, or just "No trade." Keep the source link and partial-source label. Risks, pre-trade checks, and evidence remain in the full authenticated analysis. This supersedes the longer default trade-card format below.

- 2026-11-01: Episode replies should be concise and trade-focused: instrument/direction, why, main risk, and the key pre-trade check. Keep episode recaps and evidence lists out of the default chat reply. If there is no clear trade, say so briefly. Preserve source links, partial-coverage disclosure and the validated analysis internally.

- 2026-11-01: Matthew explicitly resolved the fourth-idea ambiguity: "Research each episode and propose a trade." Do not default Dwarkesh episodes to NVDA or a seven-day hold. Research the actual claims, cite evidence, identify an available instrument, and require individual approval. A generic episode prompt must not create an executable release-date rule. Existing explicitly configured rules and runtime trading settings are not changed by this correction.

- 2026-11-01: Account-owner privacy applies even when exchange addresses are public. Do not embed participants' wallet addresses or show group balances, positions or fills before connection. Matthew explicitly chose owner-only access. PR #12's public group-account panel contradicts that instruction; remove it, keep user-added friends and connected-owner reads, and test that disconnected visitors make zero account requests.

Things Matthew corrected once. Do not make him say them twice.

- 2026-11-01: Nothing fake on the website. No practice workspace, no simulated activity or leaderboard, no placeholder
  addresses, no invented fills (the Lab no longer synthesizes a tail when a wallet has no fills). Show real positions from the
  accounts we set up, read from Hyperliquid. The demo is four ideas only (see [[decisions]]).
- 2026-11-01: Test what the site offers before calling it done: run every example and button against the live API. 5 of 8
  Lab examples were failing on protoss.trade (hourly history only reaches ~208 days) while check.sh was GREEN.
- 2026-10-31: The Lab can run on real Hyperliquid history offline: `FileCandles` reads `backend/app/data/candles/<MARKET>_1d.csv`, layered over SimCandles when the API is unreachable, and the result notes say which it used. Refresh the files from a machine that can reach api.hyperliquid.xyz (candleSnapshot, 1d).
- 2026-10-31: Name is Protoss now. Blizzard owns the StarCraft Protoss trademark; flagged once, Matthew chose it for now.
- 2026-10-31: Do not call the pooled org a phalanx (too hard to pronounce). It is a legion in copy; code stays org.
- 2026-10-31: Do not control his computer (no screen control, no clicking around). Shell and files only, and only on
  machines he linked for that purpose. He will run anything that moves money or signs with a key.
- 2026-10-31: Product name must be a unique Greek-flavored word, not something like "enablers". Now Protoss; the org is a legion.
- 2026-10-31: He prefers concise, action-oriented replies; never the words "genuinely", "honest", "honestly".
- 2026-10-31: When he says "the basketball" he means the airless basketball print, not the locker shelf. Confirm the file before slicing.
- 2026-10-31: Anti-slop on X copy is standing policy, not a one-off (see [[voice]]).
- 2026-10-31: Builder-code answer he wanted: a *separate* funded account in standard mode, not converting his personal Unified account.

- 2026-11-01: Matthew wants the practice demo to resemble the Telegram group where the product will be used, with the working group chat on the homepage. Use the same conversation component in both places: member avatars, Probe bot messages, inline idea backing, and a message composer. Keep paper status visible and state that browser messages are not sent to Telegram.

- 2026-11-01: No fake balances, positions, activity, or sample friends on the public website. Real positions are private to the connected account view. The Telegram-style practice work was superseded by this correction before publication.
