# Coliseum copy kit

Positioning line
: **Pool money with your friends. Agents trade it. Hard limits hold the line, before any order reaches the exchange.**

## Headlines (8)

Chosen for the poster: **Your friends. One wall.** (pairs with the shield-wall art; the sub-line carries the mechanics)

1. Your friends. One wall.
2. Agents fight. You set the limits.
3. Pool $100. Watch every fill.
4. No agent trades past the line you drew.
5. Draw the line. Let them fight.
6. Seven shields. One wall. Every fill public.
7. Hard limits, checked before the exchange.
8. Write the mandate. Watch the wall hold.

## Sub-lines (3)

1. Pool $100 each with your friends. AI agents trade the pot inside limits you write in plain English: leverage cap, daily-loss cap, drawdown stop, allowed markets. Every fill and every rejected order is public.
2. A leader writes one paragraph. Agents trade it on Hyperliquid perps. A 3x cap, a 12% stop and a market list are enforced in code before the order leaves the building.
3. Copy a legion, tail an agent, or backtest a hunch in plain English in the Lab. Paper mode now, real money when the wall has held.

## The mandate, as marketing copy

Original: "memory chips are mispriced vs demand; trade NVDA and SP500 perps plus BTC as a hedge; never above 3x; stop everything at 12% drawdown."

Rewritten:

> **Lee's legion. 4 depositors. $1,300 pooled.**
> The thesis: memory chips are priced below the demand curve.
> The markets: NVDA and SP500 perps, with BTC as the hedge.
> The line: never above 3x. Flatten everything at a 12% drawdown.
> The agents can argue about entries. They cannot argue with the line.

Shorter cut for a card:

> Thesis in one paragraph. Three markets. 3x cap. 12% stop. Every fill public. That is a legion.

## About (60 words)

Coliseum is a place on Hyperliquid where friends pool about $100 each into a legion. A leader writes the mandate in plain English, AI agents trade the pot, and hard limits (leverage, notional, daily loss, drawdown, allowed markets) are enforced before any order reaches the exchange. Every fill and every rejected order is public. Built by Matthew, an ex-IMC quant researcher in New York.

## Voice rules

1. Numbers over adjectives. "3x cap, 12% stop" beats "strict risk controls".
2. Say what the limit does, in the order it happens: written, checked, enforced, then the exchange.
3. Never promise returns. Describe mechanics, show fills, show rejections.
4. Rejected orders are a feature. Mention them as often as fills.
5. No em dashes. Periods and commas.
6. No hype vocabulary: no "revolutionize", "unlock", "empower", "seamless", "game-changer", "journey", "the future of".
7. One exclamation mark per campaign, at most.
8. Plain nouns from the product: legion, mandate, limit, fill, rejected order, leaderboard, Lab, builder code.
9. First person singular from the founder on social. No "we are excited".
10. Say "paper mode" or "testnet" whenever the product state is paper mode or testnet.

## Visual notes for whoever sets type

- Headline and wordmark lettering in the poster is an original chiseled block alphabet drawn as SVG paths (`brand/ad.html`, `layout()`), so the posters do not depend on a webfont. Anton (display) and Inter (body) load from Google Fonts for secondary text, with Inter Display / Inter as the fallback.
- Ink `#0a0a0a`, paper `#f4f1ea`. The one spot color is Spartan red `#C8102E`, used on under 5% of the area: the issue box, the period of the headline, the center crest. The checkbox "spot color" in `ad.html` turns it off.
- `hero.svg` is ink on transparent with paper fills on the shield faces. Inline it on dark pages and override `.ink{fill:#fff}.ink-stroke{stroke:#fff}.paper{fill:#000}.paper-stroke{stroke:#000}`. The center crest reads `--spot` for the red.
- `web/public/mark.svg` uses `currentColor`, so `color` on the parent sets the ink.
