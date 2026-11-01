import React from 'react'

export const researchIdeas = [
  { title: 'Follow a Bitcoin trend', market: 'BTC', idea: 'A sustained trend may outlast a short burst of buying.', test: 'Compare a 10/50 daily moving-average rule with buying and holding. The rule can go long or short. Reserve a later period before choosing parameters.', fails: 'The advantage disappears after costs or in the reserved period.', prompt: 'Backtest a 10/50 momentum crossover on BTC with daily bars over the last 365 days' },
  { title: 'Test Ethereum reversals', market: 'ETH', idea: 'An unusually large move may reverse toward its recent average.', test: 'Test a 20-day mean-reversion rule: buy after low readings, short after high readings. Compare with holding ETH and inspect the worst losing streak.', fails: 'Trending periods produce losses larger than the rebounds recover.', prompt: 'Backtest mean reversion on ETH with daily bars over the last 365 days' },
  { title: 'Buy gradually or all at once', market: 'BTC', idea: 'Spreading purchases may reduce entry-date risk, while leaving more cash idle.', test: 'Compare $100 weekly purchases with a lump sum. Keep the same initial budget and include idle cash.', fails: 'Lower drawdown only reflects lower exposure, with no benefit for the saver’s stated goal.', prompt: 'Buy $100 of BTC every week over the last 365 days with $10000' },
  { title: 'News before the crowd', market: 'HYPE', idea: 'A specific regulatory announcement could change demand for HYPE. This is a hypothesis, not confirmed news.', test: 'Define the official announcement, its first public timestamp, entry delay and expiry before testing.', fails: 'The move happened before the public timestamp, or similar announcements show no repeatable effect.', missing: 'Needs verified event timestamps and intraday history.' },
  { title: 'An AI valuation reset', market: 'xyz:ANT', idea: 'A pre-IPO derivative price could fall if expectations for AI companies weaken.', test: 'Define the valuation trigger, holding period, funding budget and maximum loss. A derivative is not company stock.', fails: 'The trigger never occurs, price rises, or funding consumes the expected gain.', missing: 'Needs verified market history, valuation inputs and funding. Short backtest not supported by this starter.' },
  { title: 'Crowded positions unwind', market: 'HYPE', idea: 'Extreme funding combined with rising open interest might precede a reversal.', test: 'Choose thresholds using an earlier sample, then test once on an untouched later sample.', fails: 'Funding stays extreme while price keeps trending, or costs erase the effect.', missing: 'Needs historical funding and open interest. Price candles alone cannot test this.' },
]

export default function ResearchIdeas({ onSelect }) {
  return <section className="research-ideas" aria-labelledby="research-title">
    <h2 id="research-title">Start with an idea you can disprove</h2>
    <p className="sub">Six research questions. None is a trade recommendation or a proven strategy. Review the data source in every result.</p>
    <div className="research-grid">{researchIdeas.map(item => <article className="research-card" key={item.title}>
      <span className="sub">{item.market} · {item.prompt ? 'Price-history starter' : 'Research outline'}</span>
      <h3>{item.title}</h3><p>{item.idea}</p>
      <details><summary>How to test it</summary><p>{item.test}</p><p><b>What would disprove it:</b> {item.fails}</p></details>
      {item.prompt ? <button onClick={() => onSelect(item.prompt)}>Use this idea</button> : <p className="sub">{item.missing}</p>}
    </article>)}</div>
    <p className="sub">Research background: <a href="https://www.aqr.com/insights/research/journal-article/time-series-momentum" target="_blank" rel="noreferrer">time-series momentum research</a> concerns traditional futures, not proof for these crypto rules. <a href="https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding" target="_blank" rel="noreferrer">Perpetual funding</a> can change trade outcomes and is excluded from the current Lab model.</p>
  </section>
}
