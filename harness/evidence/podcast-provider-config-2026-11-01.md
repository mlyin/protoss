# Dedicated episode provider configuration

The user saved an Anthropic credential through the private hidden prompt. Configure the bot service with PODCAST_ANTHROPIC_API_KEY so enabling episode analysis does not also enable the Lab model planner. Existing ANTHROPIC_API_KEY remains a compatibility fallback. The dedicated key takes precedence. No key value appears in this trace or Git.

Validation: dedicated-key research succeeds with an injected analysis while the Lab provider variable remains unset; precedence and existing fallback tests are retained. Runtime acceptance will call only authenticated POST /research/podcast and compare health mode before/after. No trade handler or Telegram message is needed for the test.
