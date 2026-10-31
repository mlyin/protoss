# Design

Direction (written after an unslop pass, 2026-10-31; method from unslop by Damir Sokolovsky, CC BY 4.0):

- **Product.** Friends pool money into a phalanx that agents trade inside hard limits, every fill public.
- **Character.** Stark, disciplined, a little brutal.
- **World.** Ink and newsprint. Screen-printed black-and-white comic Spartans: Corinthian helmet in profile,
  a wall of round shields with spears, halftone shading, hard shadows. The arena oval.
- **Moments.** The equity curves (Lab result, phalanx page) drawn with care; the phalanx card's mandate as a
  caption box; the hero/ad illustration. Everything else is quiet chrome.
- **Signature.** "The line you drew": a 2px Spartan-red rule marking a limit, under the halted count, under
  the limits on a phalanx card, on charts at the drawdown stop. Red appears nowhere else in the chrome.

Tokens (web/src/styles.css): warm ink ramp bg #121211, surface #181816, raised #22221f, text #efe9de,
secondary #aaa398, muted #8a847a, hairline text@8%; accent #c8102e (as text #e2334f); positive #4cc38a,
negative #e5484d, amber #d9a441. Type: Inter for interface, Anton for the wordmark and page titles only,
JetBrains Mono for figures. 4px grid, radius 8 controls / 12 cards, one easing cubic-bezier(.22,1,.36,1).

Slop here means: gradients, glows, emoji, uppercase tracked labels, pulsing dots, sparkline-stuffed stat cards,
"300"-movie trade dress, stock Spartan clip art. Original vector art only. Brand files live in `brand/`
(mark, hero, ad.html, copy.md); the mark is `web/public/mark.svg`.
