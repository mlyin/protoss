# Source-owned episode evidence

Real runtime verification of PR #37 rejected an otherwise structured report because its generated quotations failed the exact-source or aggregate quote gate. A separate call passed, demonstrating intermittent output reliability rather than a credential failure.

The provider now selects one evidence_id from up to 128 evenly spaced eight-word excerpts extracted from the fetched public text. It receives the surrounding source text and instructions to choose a supporting excerpt. The server attaches the original excerpt; no generated quote reaches the report. The strict provider schema constrains IDs and one-claim structure. Unsupported provider schema length/maxItems bounds move into descriptions, while the existing local Analysis constraints, exact-source check and market validation remain mandatory. Unknown IDs, booleans, strings and extra claim fields are rejected. No output is dispatched as an action.

This establishes literal provenance, not semantic corroboration. The source remains limited public episode text, truncated when necessary; independent verification and automatic monitoring remain separate.
