import React, { useEffect, useState } from 'react'
import { apiFetch } from './api.js'
import './IdeaChat.css'

export const IDEAS = [
  { id: 'hacks', label: 'A company gets hacked', prompt: 'Let’s buy XMR every time a major company gets hacked.', market: 'XMR', dex: '', direction: 'Long', title: 'Hacks → XMR', detail: 'The idea: after a confirmed major-company hack, consider a long XMR position. First check whether the historical reaction beats buying on an ordinary day.', risk: 'A hack does not necessarily increase demand for XMR. Define the event, entry window, and exit before trading.', event: 'Confirmed company hack', next: 'Test the historical rule' },
  { id: 'robots', label: 'Robots take over', prompt: 'I think robots are going to take over the world.', market: 'xyz:UNITREE', dex: 'xyz', direction: 'Long', title: 'Robotics → Unitree', detail: 'One market to research for that thesis is xyz:UNITREE. The proposed direction is long: your idea is that expectations for robotics companies will rise.', risk: 'This is a Unitree-linked perpetual, not Unitree shares. Its pricing can diverge from the company’s underlying value.', next: 'Review the Unitree market' },
  { id: 'anthropic', label: 'The Anthropic bubble pops', prompt: 'The Anthropic bubble is going to pop.', market: 'xyz:ANT', dex: 'xyz', direction: 'Short', title: 'Anthropic → short', detail: 'The market to research is xyz:ANT. A short expresses your view that the Anthropic-linked market price will fall.', risk: 'ANT is a perpetual, not Anthropic stock. A short loses money when the price rises; leverage can lead to liquidation.', next: 'Review the Anthropic market' },
  { id: 'dwarkesh', label: 'A new Dwarkesh episode', prompt: 'Dwarkesh is always right. Turn each new podcast into a trade idea.', title: 'New episode → trade thesis', detail: 'Use a new episode as a research trigger. Extract a concrete claim, find the related listed market, then decide on a direction, entry, and what would invalidate it. If the episode has no defensible market connection, skip the trade.', risk: 'An interview is evidence to examine, not a trading signal by itself. A persuasive claim may already be priced in.', event: 'New Dwarkesh Podcast episode', next: 'Read an episode' },
]

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
  const testHistory = async () => {
    setBusy(true); setResearch(null)
    try {
      const response = await apiFetch('/lab/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: 'what if I bought XMR every time a major institution got hacked and held 7 days', days: 730 }) })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Historical research is unavailable.')
      if (typeof result.reply !== 'string') throw new Error('The research service returned no explanation.')
      setResearch(result.reply)
    } catch (e) { setResearch(e.message || 'Historical research is unavailable. No result has been invented.') }
    finally { setBusy(false) }
  }
  return <section className="idea-demo" aria-label="Four trade ideas">
    <div className="idea-picker"><p className="sub">Start with an idea</p><h2>Four ways a<br />conversation starts.</h2>
      <div role="tablist" aria-label="Trade idea">{IDEAS.map((item, i) => <button id={`tab-${item.id}`} key={item.id} role="tab" aria-controls="idea-conversation" aria-selected={selected === item.id} onClick={() => { setSelected(item.id); setResearch(null) }} disabled={busy}><span>0{i + 1}</span>{item.label}<span aria-hidden="true">↗</span></button>)}</div>
      <p className="idea-picker-note">Idea previews, not executed trades. Your real positions stay in your connected account.</p>
    </div>
    <div className="idea-conversation" role="tabpanel" id="idea-conversation" aria-labelledby={`tab-${idea.id}`}>
      <header><img src="/probe/idle.svg" alt="" /><div><b>Protoss</b><span>From a conversation to a trade idea</span></div><span className="idea-draft-label">Draft</span></header>
      <div className="idea-chat-body">
        <div className="idea-user-bubble">{idea.prompt}</div>
        <div className="idea-bot-bubble"><span className="idea-bot-name">Probe</span><h3>{idea.title}</h3><p>{idea.detail}</p>
          {idea.market && <MarketQuote key={idea.id} idea={idea} />}
          {idea.event && <div className="idea-event"><b>Research trigger</b><span>{idea.event}</span><small>{idea.id === 'dwarkesh' ? 'Episode monitoring is not connected. No podcast has been analyzed by this preview.' : 'This preview does not monitor news or place recurring orders.'}</small></div>}
          <p className="idea-risk">{idea.risk}</p>
          {idea.id === 'hacks' ? <button className="idea-action" onClick={testHistory} disabled={busy}>{busy ? 'Checking history…' : idea.next}</button> : <a className="idea-action" href={idea.market ? `https://app.hyperliquid.xyz/trade/${encodeURIComponent(idea.market)}` : 'https://www.dwarkesh.com/podcast'} target="_blank" rel="noreferrer">{idea.next} ↗</a>}
        </div>
        {research && <div className="idea-bot-bubble" role="status"><span className="idea-bot-name">Research response</span><p className="idea-research">{research}</p></div>}
      </div>
      <footer><span>Each person decides and approves their own trade.</span><a href="/app/">My positions ↗</a></footer>
    </div>
  </section>
}
