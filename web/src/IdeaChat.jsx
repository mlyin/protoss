import React, { useEffect, useState } from 'react'
import { apiFetch } from './api.js'
import './IdeaChat.css'

export const TELEGRAM_BOT = 'https://t.me/ProtossTradingDemoBot'

// Same four sentences, same order, as the Lab (backend/app/lab.py EXAMPLES) and the Telegram bot's /demo menu.
export const IDEAS = [
  { id: 'hacks', label: 'A company gets hacked', prompt: "Let's buy XMR every time a major company gets hacked", market: 'XMR', dex: '', direction: 'Long', title: 'Hacks → XMR for a day', ask: 'buy XMR after major hacks, hold 1 day, over the last 180 days using hourly candles', days: 180, event: 'A major company gets hacked', when: 'In the Telegram group, someone reports it ("protoss hack: …") and every armed copy buys XMR for one day.', risk: 'A hack does not have to raise demand for XMR. The test above says whether it has.' },
  { id: 'robots', label: 'Robots take over', prompt: 'I think robots are going to take over the world', market: 'xyz:UNITREE', dex: 'xyz', direction: 'Long', title: 'Robotics → Unitree', ask: 'buy and hold xyz:UNITREE over the last 80 days', days: 80, risk: 'xyz:UNITREE is a Unitree-linked perpetual, not Unitree shares. It can move away from the company’s value.' },
  { id: 'anthropic', label: 'The Anthropic bubble pops', prompt: 'The Anthropic bubble is going to pop', market: 'xyz:ANT', dex: 'xyz', direction: 'Short', title: 'Anthropic → short', risk: 'xyz:ANT is a perpetual, not Anthropic stock. A short loses money when the price rises.' },
  { id: 'dwarkesh', label: 'A new Dwarkesh episode', prompt: 'Research each new Dwarkesh episode and propose a trade', researchOnly: true, title: 'An episode → a researched idea', event: 'A new Dwarkesh Podcast episode', when: 'Read the episode, check its claims against sources, then propose a relevant trade for each person to review.', risk: 'A new episode alone does not choose a market or direction. The research may find no trade worth proposing.' },
]

// What a live answer must be to count as this idea; anything else (an older Lab, a clarifying question) is not shown as a result.
const EXPECT = {
  hacks: spec => spec?.event_set === 'major_hacks' && spec?.market === 'XMR',
  robots: spec => spec?.market === 'xyz:UNITREE' && spec?.side !== 'short',
  anthropic: spec => spec?.market === 'xyz:ANT' && spec?.side === 'short',
}

function useSnapshot() {
  // scripts/idea_snapshots.py: the same backtest and chart the Telegram bot shows, run on Hyperliquid candles
  const [snap, setSnap] = useState(undefined)
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
  const tested = !idea.researchOnly && snap?.ideas?.find(i => i.id === selected)
  const testHistory = async () => {
    setBusy(true); setResearch(null)
    try {
      // the hacks test asks for 180 days on hourly candles, which the public API can always serve (PR #10)
      const response = await apiFetch('/lab/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: idea.ask || idea.prompt, ...(idea.days ? { days: idea.days } : {}) }) })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Historical research is unavailable.')
      if (typeof result.reply !== 'string') throw new Error('The research service returned no explanation.')
      if (result.kind !== 'error' && !(result.kind === 'backtest' && EXPECT[idea.id]?.(result.spec))) {
        const when = snap?.as_of ? new Date(snap.as_of).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'earlier'
        throw new Error(`The live Lab can't run this idea yet; it is being updated. The test above ran on ${when} with the same Hyperliquid prices.`)
      }
      const baseline = Array.isArray(result.result?.notes) ? result.result.notes.filter(note => typeof note === 'string' && note.startsWith('baseline:')) : []
      setResearch([result.reply, ...baseline].join('\n\n'))
    } catch (e) { setResearch(e.message || 'Historical research is unavailable. No result has been invented.') }
    finally { setBusy(false) }
  }
  return <section className="idea-demo" aria-label="Four trade ideas">
    <div className="idea-picker"><p className="sub">Start with an idea</p><h2>Four ways a <br />conversation starts.</h2>
      <div role="tablist" aria-label="Trade idea">{IDEAS.map((item, i) => <button id={`tab-${item.id}`} key={item.id} role="tab" aria-controls="idea-conversation" aria-selected={selected === item.id} onClick={() => { setSelected(item.id); setResearch(null) }} disabled={busy}><span>0{i + 1}</span>{item.label}<span aria-hidden="true">↗</span></button>)}</div>
      <p className="idea-picker-note">Discuss an idea, check the evidence, then decide. Each person approves their own trade.</p>
    </div>
    <div className="idea-conversation" role="tabpanel" id="idea-conversation" aria-labelledby={`tab-${idea.id}`}>
      <header><img src="/probe/idle.svg" alt="" /><div><b>Protoss</b><span>From a conversation to a trade idea</span></div></header>
      <div className="idea-chat-body">
        <div className="idea-user-bubble">{idea.prompt}</div>
        <div className="idea-bot-bubble"><span className="idea-bot-name">Probe</span><h3>{idea.title}</h3>
          {tested?.why && <p>{tested.why}</p>}
          {tested && <picture><source media="(max-width: 600px)" srcSet={`/ideas/${idea.id}-phone.png`} width="1080" height="1350" />
            <img className="idea-card" src={`/ideas/${idea.id}.png`} alt={`${tested.label}: backtest chart against buy and hold`} width="1200" height="630" /></picture>}
          {!idea.researchOnly && (tested ? <div className="idea-verdict">{tested.verdict.map((line, i) => <p key={i}>{line}</p>)}<small>Tested on Hyperliquid candles, fees and slippage included, funding not · {new Date(snap.as_of).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</small></div>
            : <p className="idea-risk">{snap === undefined ? 'Loading the test…' : 'The saved test is unavailable. Run it now for a fresh one.'}</p>)}
          {idea.researchOnly && <p className="idea-risk" role="status">Episode monitoring and transcript research are not connected yet. Share an episode and a specific claim in Telegram to start the discussion. No market or trade has been selected.</p>}
          {tested?.events?.length > 0 && <details className="idea-events"><summary>The {tested.events.length} {idea.id === 'hacks' ? 'hacks' : 'episodes'} it was tested on</summary>
            <table><tbody>{tested.events.map(e => <tr key={e.date}><td>{e.date}</td><td className={e.move_pct > 0 ? 'up' : 'down'}>{e.move_pct > 0 ? '+' : ''}{e.move_pct.toFixed(1)}%</td><td>{e.what}</td></tr>)}</tbody></table></details>}
          {idea.market && <MarketQuote key={idea.id} idea={idea} />}
          {idea.event && <div className="idea-event"><b>What sets it off</b><span>{idea.event}</span><small>{idea.when}</small></div>}
          <p className="idea-risk">{idea.risk}</p>
          <div className="idea-actions">{!idea.researchOnly && <button className="idea-action" onClick={testHistory} disabled={busy}>{busy ? 'Running on live prices…' : 'Run it now'}</button>}<a className="idea-action primary" href={TELEGRAM_BOT} target="_blank" rel="noreferrer">{idea.researchOnly ? 'Discuss an episode in Telegram ↗' : 'Trade it in Telegram ↗'}</a></div>
        </div>
        {research && <div className="idea-bot-bubble" role="status"><span className="idea-bot-name">Research response</span><p className="idea-research">{research}</p></div>}
      </div>
      <footer><span>Each person decides and approves their own trade.</span><a href="/app/">My positions ↗</a></footer>
    </div>
  </section>
}
