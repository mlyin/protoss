// The four ideas Protoss demos (Matthew, 2026-11-01). Same sentences, same order, as the Lab's examples
// (backend/app/lab.py EXAMPLES) and the Telegram bot's /demo menu (scripts/telegram_bridge.py IDEAS).

export const TELEGRAM_BOT = 'https://t.me/ProtossTradingDemoBot'

export const IDEAS = [
  { said: "Let's buy XMR every time a major company gets hacked", trade: 'Buy XMR after each major hack, hold 7 days.', market: 'XMR' },
  { said: 'I think robots are going to take over the world', trade: 'Buy and hold Unitree, the humanoid robot maker.', market: 'xyz:UNITREE' },
  { said: 'The Anthropic bubble is going to pop', trade: 'Short the Anthropic-linked perp. Not Anthropic shares.', market: 'xyz:ANT' },
  { said: 'Dwarkesh is always right. Trade every new episode', trade: 'Buy NVDA on each new Dwarkesh Podcast episode, hold 7 days.', market: 'xyz:NVDA' },
]

export const labLink = (said) => `/app/#/lab?idea=${encodeURIComponent(said)}&run=1`
