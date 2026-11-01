import React, { useEffect, useState } from 'react'
import { apiFetch } from './api.js'
import './IdeaChat.css'

export const TELEGRAM_BOT = 'https://t.me/ProtossTradingDemoBot'

// Same four sentences, same order, as the Lab (backend/app/lab.py EXAMPLES) and the Telegram bot's /demo menu.
export const IDEAS = [
  { id: 'hacks', label: 'A company gets hacked', prompt: "Let's buy XMR every time a major company gets hacked", market: 'XMR', dex: '', direction: 'Long', title: 'Hacks → XMR for a day', event: 'A major company gets hacked', when: 'In the Telegram group, someone reports it ("protoss hack: …") and every armed copy buys XMR for one day.', risk: 'A hack does not have to raise demand for XMR. The test below says whether it has.' },
  { id: 'robots', label: 'Robots take over', prompt: 'I think robots are going to take over the world', market: 'xyz:UNITREE', dex: 'xyz', direction: 'Long', title: 'Robotics → Unitree', risk: 'xyz:UNITREE is a Unitree-linked perpetual, not Unitree shares. It can move away from the company’s value.' },
  { id: 'anthropic', label: 'The Anthropic bubble pops', prompt: 'The Anthropic bubble is going to pop', market: 'xyz:ANT', dex: 'xyz', direction: 'Short', title: 'Anthropic → short', risk: 'xyz:ANT is a perpetual, not Anthropic stock. A short loses money when the price rises.' },
  { id: 'dwarkesh', label: 'A new Dwarkesh episode', prompt: 'Dwarkesh is always right. Trade every new episode', market: 'xyz:NVDA', dex: 'xyz', direction: 'Long', title: 'New episode → NVDA for 7 days', event: 'A new Dwarkesh Podcast episode', when: 'The Telegram bot reads his podcast feed every 10 minutes. A new episode buys NVDA for 7 days in every armed copy.', risk: 'An interview is not a price signal by itself. 33 episodes is a small sample.' },
]

function useSnapshot() {
  // scripts/idea_snapshots.py: the same backtest and chart the Telegram bot shows, run on Hyperliquid candles
  const [snap, setSnap] = useState(null)
  useEffect(() => { fetch('/ideas/ideas.json', { credentials: 'omit' }).then(r => (r.ok ? r.json() : null)).then(setSnap).catch(() => setSnap(null)) }, [])
  return snap
}

function MarketQuote({ idea }) {
  const [quote, setQuote] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!idea.market) return
    let alive = true, timer
    const controller = new AbortController()
    const load = async () => {
      try {
        const response = await fetch('https://api.hyperliquid.xyz/info', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: 'metaAndAssetCtxs', dex: idea.dex }), signal: controller.signal, credentials: 'omit' })
        if (!response.ok) throw new Error('Market data is unavailable. No quote is shown.')
        const [meta, contexts] = await response.json()
        const index = meta.universe.findIndex(asset => asset.name === idea.market && !asset.isDelisted)
        const mark = contexts[index]?.markPx
        if (index < 0 || !Number.isFinite(Number(mark)) || Number(mark) <= 0) throw new Error('This market is not currently available.')
        if (alive) { setQuote({ mark, time: new Date() }); setError('') }
      } catch (e) { if (alive) { setQuote(null); setError(e.message) } }
      finally { if (alive) timer = setTimeout(load, 30000) }
    }
    load()
    return () => { alive = false; controller.abort(); clearTimeout(timer) }
  }, [idea.id])
  return <div className="idea-quote"><div><span>Proposed direction</span><b>{idea.direction} {idea.market}</b></div><div><span>Hyperliquid mark</span><b>{quote ? new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(Number(quote.mark)) : 'Unavailable'}</b></div>{quote && <small>Read at {quote.time.toLocaleTimeString()} · Indicative price, not an execution quote</small>}{error && <small role="status">{error}</small>}</div>
}

export default function IdeaChat() {
  const [selected, setSelected] = useState('hacks')
  const [research, setResearch] = useState(null)
  const [busy, setBusy] = useState(false)
  const idea = IDEAS.find(i => i.id === selected)
  const snap = useSnapshot()
  const tested = snap?.ideas?.find(i => i.id === selected)
  const testHistory = async () => {
    setBusy(true); setResearch(null)
    try {
      const response = await apiFetch('/lab/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: idea.prompt }) })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Historical research is unavailable.')
      if (typeof result.reply !== 'string') throw new Error('The research service returned no explanation.')
      setResearch(result.reply)
    } catch (e) { setResearch(e.message || 'Historical research is unavailable. No result has been invented.') }
    finally { setBusy(false) }
  }
  return <section className="idea-demo" aria-label="Four trade ideas">
    <div className="idea-picker"><p className="sub">Start with an idea</p><h2>Four ways a <br />conversation starts.</h2>
      <div role="tablist" aria-label="Trade idea">{IDEAS.map((item, i) => <button id={`tab-${item.id}`} key={item.id} role="tab" aria-controls="idea-conversation" aria-selected={selected === item.id} onClick={() => { setSelected(item.id); setResearch(null) }} disabled={busy}><span>0{i + 1}</span>{item.label}<span aria-hidden="true">↗</span></button>)}</div>
      <p className="idea-picker-note">Each test runs on real Hyperliquid prices. Trades happen in Telegram, one order from each person's own account.</p>
    </div>
    <div className="idea-conversation" role="tabpanel" id="idea-conversation" aria-labelledby={`tab-${idea.id}`}>
      <header><img src="/probe/idle.svg" alt="" /><div><b>Protoss</b><span>From a conversation to a trade idea</span></div></header>
      <div className="idea-chat-body">
        <div className="idea-user-bubble">{idea.prompt}</div>
        <div className="idea-bot-bubble"><span className="idea-bot-name">Probe</span><h3>{idea.title}</h3>
          {tested?.why && <p>{tested.why}</p>}
          {tested && <img className="idea-card" src={`/ideas/${idea.id}.png`} alt={`${tested.label}: backtest chart against buy and hold`} width="1200" height="630" />}
          {tested ? <div className="idea-verdict">{tested.verdict.map((line, i) => <p key={i}>{line}</p>)}<small>Tested on Hyperliquid candles, fees and slippage included, funding not · {new Date(snap.as_of).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</small></div>
            : <p className="idea-risk">{snap === null ? 'Loading the test…' : 'The saved test is unavailable. Run it now for a fresh one.'}</p>}
          {tested?.events?.length > 0 && <details className="idea-events"><summary>The {tested.events.length} {idea.id === 'hacks' ? 'hacks' : 'episodes'} it was tested on</summary>
            <table><tbody>{tested.events.map(e => <tr key={e.date}><td>{e.date}</td><td className={e.move_pct > 0 ? 'up' : 'down'}>{e.move_pct > 0 ? '+' : ''}{e.move_pct.toFixed(1)}%</td><td>{e.what}</td></tr>)}</tbody></table></details>}
          {idea.market && <MarketQuote key={idea.id} idea={idea} />}
          {idea.event && <div className="idea-event"><b>What sets it off</b><span>{idea.event}</span><small>{idea.when}</small></div>}
          <p className="idea-risk">{idea.risk}</p>
          <div className="idea-actions"><button className="idea-action" onClick={testHistory} disabled={busy}>{busy ? 'Running on live prices…' : 'Run it now'}</button><a className="idea-action primary" href={TELEGRAM_BOT} target="_blank" rel="noreferrer">Trade it in Telegram ↗</a></div>
        </div>
        {research && <div className="idea-bot-bubble" role="status"><span className="idea-bot-name">Research response</span><p className="idea-research">{research}</p></div>}
      </div>
      <footer><span>Each person decides and approves their own trade.</span><a href="/app/">My positions ↗</a></footer>
    </div>
  </section>
}
