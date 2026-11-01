import { apiFetch as fetch } from './api.js'
import React, { useEffect, useRef, useState } from 'react'
import { SkelLines } from './ui.jsx'
import { IDEAS, TELEGRAM_BOT } from './ideas.js'

// The Lab: say an idea in plain English, get a backtest on real Hyperliquid history back.
// Talks to POST /lab/chat (see backend/app/lab.py for the contract).

const fmtUsd = (v) => (v == null ? '—' : '$' + Number(v).toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) < 100 ? 2 : 0 }))
const fmtPct = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%')
const cls = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '')
const day = (iso) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })

function Curve({ a, b, w = 640, h = 180 }) {
  if (!a || a.length < 2) return null
  const all = [...a.map((p) => p[1]), ...((b || []).map((p) => p[1]))]
  const lo = Math.min(...all), hi = Math.max(...all)
  const t0 = new Date(a[0][0]).getTime(), t1 = new Date(a[a.length - 1][0]).getTime()
  const X = (iso) => ((new Date(iso).getTime() - t0) / Math.max(1, t1 - t0)) * (w - 2) + 1
  const Y = (v) => h - 4 - ((v - lo) / Math.max(1e-9, hi - lo)) * (h - 8)
  const path = (pts) => pts.map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ')
  const start = a[0][1]
  return (
    <svg className="curve" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="equity curve">
      <line x1="0" x2={w} y1={Y(start)} y2={Y(start)} className="curve-base" />
      {b && <path d={path(b)} className="curve-bench" />}
      <path d={path(a)} className={`curve-main ${a[a.length - 1][1] >= start ? 'up' : 'down'}`} />
    </svg>
  )
}

function Result({ r }) {
  return (
    <div className="result">
      <div className="result-head">
        <b>{r.label}</b>
        <span className="sub">{r.market} · {day(r.start)} → {day(r.end)} · {r.bars} bars · {r.trades} trades</span>
      </div>
      <div className="statrow">
        <div><span className="label">Return</span><span className={`value ${cls(r.return_pct)}`}>{fmtPct(r.return_pct)}</span></div>
        <div><span className="label">Max drawdown</span><span className="value neg">{r.max_drawdown_pct != null ? `-${Math.abs(r.max_drawdown_pct).toFixed(1)}%` : '—'}</span></div>
        <div><span className="label">Sharpe</span><span className="value">{r.sharpe ?? '—'}</span></div>
        <div><span className="label">Win rate</span><span className="value">{r.win_rate_pct != null ? `${r.win_rate_pct.toFixed(0)}%` : '—'}</span></div>
        <div><span className="label">Final</span><span className="value">{fmtUsd(r.final_equity)}</span><span className="sub">from {fmtUsd(r.starting_equity)}</span></div>
      </div>
      <Curve a={r.equity_curve} b={r.benchmark_curve} />
      {r.benchmark_curve && <div className="legend"><span className="sw main" /> strategy <span className="sw bench" /> buy &amp; hold {r.market}</div>}
      {r.trades_sample?.length > 0 && (
        <details>
          <summary className="sub">Sample fills ({r.trades_sample.length})</summary>
          <div className="tablewrap"><table className="mini">
            <thead><tr><th>When</th><th>Side</th><th className="num">Price</th><th className="num">Size</th><th>Why</th></tr></thead>
            <tbody>{r.trades_sample.map((t, i) => <tr key={i}><td>{day(t.ts)}</td><td className={t.side === 'buy' ? 'pos' : 'neg'}>{t.side}</td><td className="num">{Number(t.px).toLocaleString()}</td><td className="num">{Number(t.size).toFixed(4)}</td><td className="text sub">{t.reason}</td></tr>)}</tbody>
          </table></div>
        </details>
      )}
      {r.notes?.length > 0 && <ul className="notes">{r.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
    </div>
  )
}

export default function Lab({ initialPrompt = '', autorun = false }) {
  const [msgs, setMsgs] = useState([{ role: 'ai', text: 'Say an idea in plain words, or tap one of the four below. The test runs on real Hyperliquid candles with trading fees and slippage. Funding is not modelled, and a past result is not a promise.' }])
  const [q, setQ] = useState(initialPrompt)
  const inputRef = useRef(null)
  const ran = useRef(false)
  useEffect(() => { setQ(initialPrompt) }, [initialPrompt])
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)

  useEffect(() => { if (msgs.length > 1) endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])
  useEffect(() => { if (autorun && initialPrompt && !ran.current) { ran.current = true; ask(initialPrompt) } }, [autorun, initialPrompt])

  async function ask(text) {
    const t = (text || q).trim()
    if (!t || busy) return
    setQ('')
    setMsgs((m) => [...m, { role: 'me', text: t }])
    setBusy(true)
    try {
      const r = await fetch('/lab/chat', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ message: t }) })
      const j = await r.json()
      setMsgs((m) => [...m, { role: 'ai', text: j.reply || j.detail || 'No reply', result: j.result, kind: j.kind }])
    } catch (e) {
      setMsgs((m) => [...m, { role: 'ai', text: `The Lab is unreachable (${e.message}).`, kind: 'error' }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="lab narrow">
      <div className="lab-head">
        <h1>Test your idea</h1>
        <p className="sub">Check an idea against real history before anyone puts money in. Then take it to the group in <a href={TELEGRAM_BOT} target="_blank" rel="noreferrer">Telegram</a>.</p>
      </div>
      <div className="thread">
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">
              <div className={m.kind === 'error' ? 'neg' : ''}>{m.text}</div>
              {m.result && <Result r={m.result} />}
            </div>
          </div>
        ))}
        {busy && <div className="msg ai"><div className="bubble"><SkelLines n={3} widths={['45%', '80%', '60%']} /></div></div>}
        <div ref={endRef} />
      </div>
      <div className="ideas compact">{IDEAS.map((idea) => (
        <button key={idea.market} className="card idea" onClick={() => ask(idea.said)} disabled={busy}>
          <b>“{idea.said}”</b><span className="sub">{idea.trade}</span>
        </button>
      ))}</div>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); ask() }}>
        <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder="what if I…" disabled={busy} aria-label="Your what-if" />
        <button className="primary" disabled={busy || !q.trim()}>Run</button>
      </form>
    </section>
  )
}
