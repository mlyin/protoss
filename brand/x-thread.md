# Coliseum launch thread (X)

## Anti-slop checklist (applies to every post below)

- [x] R1. None of: "excited to announce", "thrilled", "game-changer", "revolutionize", "unlock", "empower", "seamless", "journey", "dive in", "delve", "landscape", "in today's", "it's not X, it's Y", "the future of"
- [x] R2. No emoji, no hashtags, no rocket or fire, no thread emoji
- [x] R3. No em dashes anywhere. Periods or commas. At most one exclamation mark in the whole thread
- [x] R4. Every post carries a concrete noun or number (a limit, a fill, a dollar amount, a market). No post is pure abstraction
- [x] R5. Post 1 says what it is in one sentence a trader would say to a friend. Post 2 is a specific scenario with numbers (Lee's legion: $1,300 pooled, 4 depositors, 3x cap, 12% stop, NVDA + SP500 + BTC)
- [x] R6. One post on what it is NOT (not a fund, not strangers holding your wallet, not an AI without limits)
- [x] R7. One post on builder-code economics in plain numbers (0.03% of notional)
- [x] R8. First person singular, founder voice, lowercase ok. No corporate "we are". No CTA except one "DM me if you want in on the first 20 legions" at the end
- [x] R9. No return claims, no "guaranteed", no financial-advice framing. Says plainly that it is testnet / paper mode now
- [x] R10. Every post is 260 characters or fewer

## Thread (9 posts)

1. i built a thing where you and your friends each put in about $100, an AI agent trades the pot on Hyperliquid perps, and it physically cannot trade past the limits you wrote down. it's called Coliseum. the pool is a legion.

2. example. Lee's legion: 4 depositors, $1,300 pooled. his mandate, one paragraph: memory chips are priced below demand. trade NVDA and SP500 perps, BTC as the hedge. never above 3x. flatten everything at a 12% drawdown. that paragraph is the whole brief.

3. the limits are not a prompt. leverage cap, notional cap, daily-loss cap, drawdown flatten and the allowed-market list are checked in code before an order is sent to the exchange. an agent that asks for 5x on Lee's pool gets a rejected order, not a warning.

4. every fill and every rejected order goes on a public leaderboard. when an agent asks for 4x against a 3x cap you see the rejected order and the reason. you can copy-trade a legion you like or tail one agent. nothing happens off the board.

5. there is a Lab. it's a chat box for backtests in plain English. "what if i bought XMR every time a major company got hacked?" "what if i tailed this wallet for the last 90 days?" you get a curve, a drawdown number and the trade list.

6. what Coliseum is not. not a fund, nobody manages your money. not custody, no stranger holds your wallet, the keys stay with you. not an AI that trades without limits, every order passes the line you drew or it does not exist.

7. how i get paid: a Hyperliquid builder code. 0.03% of routed notional. a legion that turns over $100k in a month pays $30. no management fee, no carry, no token. if nobody trades, i make nothing, which is the right incentive.

8. status: testnet and paper mode right now. agents trade paper on live prices, limits run for real, the leaderboard is public. no live money until i have watched the wall hold through a few ugly weeks. no returns to show you and i will not pretend otherwise.

9. i'm Matthew, ex-IMC quant researcher, building this from Queens and raising through Alliance. DM me if you want in on the first 20 legions.

## Standalone post variants (5)

A. a 12% drawdown stop that lives in a prompt is a suggestion. a 12% drawdown stop that runs before the order hits Hyperliquid is a wall. Coliseum does the second one.

B. (post this with real numbers from the leaderboard, never invented ones) Lee's legion, paper mode, week [n]: [fills] fills, [rejected] rejected orders, max leverage touched [x] against a 3x cap. the rejections are the point. every one is public.

C. four friends, $100 each, one paragraph of thesis, three markets, one hard line. that is the whole product. the rest is a leaderboard.

D. the Lab answered "what if i bought XMR every time a major company got hacked" in about 40 seconds, with the trade list. then i asked what the max drawdown was. that is the loop i want people in.

E. builder-code math for anyone curious: 0.03% of notional. $1,300 pool at 2x turning over weekly is about $10 a month to me. the whole business is many small walls, not one big fund.

## Reply-bait questions (3)

1. what is the one limit you would never let an agent cross with your money: leverage cap, daily loss, or drawdown stop? pick one and give me the number, 3x, 2%, 12%, whatever yours is.

2. if your 4 closest trading friends pooled $100 each and wrote one paragraph of thesis, what would the paragraph say? markets and the stop, please.

3. audit request for quant people: 0.03% of routed notional, no management fee, no carry. what breaks at scale, the economics or the limits engine?

## Self-audit

Run with the script at the bottom of this file against the 9 thread posts, the 5 variants and the 3 questions.

| Rule | Result | Note |
|---|---|---|
| R1 banned phrases | pass | 0 matches across 17 posts |
| R2 emoji / hashtags | pass | 0 emoji, 0 "#" |
| R3 em dashes / exclamation | pass | 0 em dashes, 0 exclamation marks |
| R4 concrete noun or number in every post | pass | each post has at least one of: $ amount, %, x leverage, market ticker, fill, rejected order, leaderboard |
| R5 post 1 one-sentence pitch, post 2 Lee's numbers | pass | post 2 has $1,300, 4 depositors, 3x, 12%, NVDA, SP500, BTC |
| R6 what it is NOT | pass | post 6; written as a list of nots plus a mechanic, not the "it's not X, it's Y" construction |
| R7 builder-code economics | pass | post 7: 0.03% of routed notional, $100k turnover pays $30 |
| R8 first person singular, one CTA | pass | "we are" does not appear; the only CTA is the last sentence of post 9 |
| R9 no return claims, paper mode stated | pass | post 8 says testnet and paper mode; no "guaranteed", no returns |
| R10 length | pass | longest thread post is 256 chars (posts 3 and 8); all variants and questions under 260 |

Fixes made during the audit: post 4 and variant B first quoted specific fills and rejections that had not happened; rewritten as mechanics / a template to fill with real leaderboard numbers. reply question 3 first used the word "honest"; it was rewritten to "audit request". Variant B and post 4 first carried invented leaderboard numbers and an invented "tuesday" rejection; both were rewritten so the only numbers are the mandate limits, and variant B now has [placeholders] to fill from the real leaderboard. Post 2 was trimmed from 262 to 253 characters. Reply question 1 got example numbers (3x, 2%, 12%) so it carries a concrete number like every other post.

### Audit script

```js
// node audit.js x-thread.md
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const posts = [...src.matchAll(/^(?:\d\.|[A-E]\.) (.+)$/gm)].map(m => m[1]);
const banned = ["excited to announce","thrilled","game-changer","revolutionize","unlock","empower","seamless","journey","dive in","delve","landscape","in today's","the future of"];
let fails = 0;
posts.forEach((p, i) => {
  const hits = banned.filter(b => p.toLowerCase().includes(b));
  const notXitsY = /it'?s not [^.,]+, it'?s /i.test(p);
  const emoji = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(p);
  const problems = [
    hits.length && 'banned:' + hits.join(','), notXitsY && 'not-X-its-Y', emoji && 'emoji',
    p.includes('#') && 'hashtag', p.includes('\u2014') && 'em dash', /\bwe are\b/i.test(p) && 'we are',
    /guarantee/i.test(p) && 'guarantee', p.length > 260 && 'len ' + p.length,
    !/\d|\bfill|\border|\bleaderboard|\bNVDA|\bBTC|\bSP500|\bXMR|\bHyperliquid/.test(p) && 'no concrete noun',
  ].filter(Boolean);
  if (problems.length) { fails++; console.log('post', i + 1, problems.join(' | ')); }
});
console.log(posts.length, 'posts,', fails, 'failing, exclamation marks:', (posts.join('').match(/!/g) || []).length);
```
