# Design

Direction (written after an unslop pass, 2026-10-31; method from unslop by Damir Sokolovsky, CC BY 4.0):

- **Product.** Friends pool money into a legion that agents trade inside hard limits, every fill public.
- **Character.** Stark, disciplined, a little brutal.
- **World.** Ink and newsprint. Screen-printed black-and-white comic Spartans: Corinthian helmet in profile,
  a wall of round shields with spears, halftone shading, hard shadows. The arena oval.
- **Moments.** The equity curves (Lab result, legion page) drawn with care; the legion card's mandate as a
  caption box; the hero/ad illustration. Everything else is quiet chrome.
- **Signature.** "The line you drew": a 2px Spartan-red rule marking a limit, under the halted count, under
  the limits on a legion card, on charts at the drawdown stop. Red appears nowhere else in the chrome.

Tokens (web/src/styles.css): warm ink ramp bg #121211, surface #181816, raised #22221f, text #efe9de,
secondary #aaa398, muted #8a847a, hairline text@8%; accent #c8102e (as text #e2334f); positive #4cc38a,
negative #e5484d, amber #d9a441. Type: Inter for interface, Anton for the wordmark and page titles only,
JetBrains Mono for figures. 4px grid, radius 8 controls / 12 cards, one easing cubic-bezier(.22,1,.36,1).

Slop here means: gradients, glows, emoji, uppercase tracked labels, pulsing dots, sparkline-stuffed stat cards,
"300"-movie trade dress, stock Spartan clip art. Original vector art only. Brand files live in `brand/`
(mark, hero, ad.html, copy.md); the mark is `web/public/mark.svg`.

- 2026-10-31: Brand kit shipped in `brand/`: `hero.svg` (7-shield legion, procedural halftone; `.ink`/`.paper` classes so an
  inlined copy inverts on dark pages, center crest reads `--spot`), `mark.svg` (helmet breaking the arena ring, `currentColor`),
  `ad.html` (1080x1350 + 1200x628; headline set in an original chiseled block alphabet drawn as SVG polygons, so it needs no
  webfont), `copy.md`, `x-thread.md`. Spot red appears on the issue box, the headline period and the center crest only (~1.5% of area).
  Chosen headline: "Your friends. One wall." Editable canvas: the "Protoss Ads" Design artifact (Anton stands in for the block alphabet there).
- 2026-10-31: Matthew wants the practice flow to look like the real product and the gold-and-cyan Probe brand. Keep the app shell, trade review and visual language consistent; show practice status clearly. Public homepage and character galleries should not expose SVG download controls.
- 2026-10-31: Matthew approved publishing the gold-and-cyan Zealot, Stalker, Immortal and Colossus roster alongside the Probe on the public homepage. Source sheet is retained in the MacBook workspace brand-concepts; the public page uses docs/probe/crew.webp.
- 2026-10-31: Correction from Matthew: a large character roster and standalone mascot gallery do not explain the product. Keep concept art saved; use characters at a useful scale within actual product activity, with a clear role. The homepage should explain and lead into the same experience the app provides. Do not advertise a practice route that the deployed app does not support. Removed both public galleries and the unsupported demo CTA; Telegram and the browser home remain the public entry points.
