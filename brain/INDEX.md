# Protoss brain

One folder of notes about the business. Every agent reads it before working and keeps it current.
Plain markdown, `[[wikilinks]]`, opens as an Obsidian vault. Dated lines, newest first inside each page.

| Page | What it holds | Read it when |
| --- | --- | --- |
| [[product]] | what Protoss is, for whom, how it makes money, the words we use | any task |
| [[voice]] | how Matthew writes, banned words, examples | writing anything a person will read |
| [[design]] | visual direction, tokens, motifs, what is slop here | touching the web app, the ad, the deck |
| [[runbooks]] | how every job gets done, step by step | running, deploying, releasing, testing |
| [[decisions]] | decisions and why, dated | before proposing a change of direction |
| [[corrections]] | things Matthew corrected once; never repeat them | always, it is short |
| [[swipe]] | hooks, headlines, ads and threads that worked (ours and the niche's) | marketing copy |
| [[people]] | business context on the people around the project | the raise, partnerships |
| content/ | every piece of content we shipped, verbatim | reuse, consistency |

How to add: append a dated line (`- 2026-10-31: ...`) to the right page. A new recurring job gets a
runbook. A correction gets one line in [[corrections]] and, if it changes a rule, the rule page too.
`python scripts/brain.py remember "..."` appends to corrections with the date; `brain.py decide "..."` to decisions.
- `brain/handoff.md`: state of the world on 2026-10-31 and the open threads, for a session starting fresh. Read it first after this index.
- 2026-10-31: the group chat (huddle) and the iMessage bridge: [[product]] (The group chat), [[runbooks]] (iMessage group chat), [[decisions]] (iMessage route).
