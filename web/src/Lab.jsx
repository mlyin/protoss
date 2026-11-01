import React, { useEffect, useRef, useState } from 'react'
import { SkelLines } from './ui.jsx'
import Probe from './Probe.jsx'

// The Lab: ask a what-if in plain English, get a backtest back, deploy it as an agent.
// Talks to POST /lab/chat (see backend/app/lab.py for the contract).

const fmtUsd = (v) => (v == null ? '—' : '$' + Number(v).toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) < 100 ? 2 : 0 }))
const fmtPct = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%')
const cls = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '')
const day = (iso) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

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

function Result({ r, deployable }) {
  const [copied, setCopied] = useState(false)
  const yaml = deployable && `  - name: ${deployable.name}\n    strategy: "${deployable.strategy.replace(/"/g, "'")}"\n    script: agents/${deployable.strategy.toLowerCase().includes('revers') ? 'meanrev' : 'momentum'}.py\n    markets: [${deployable.markets.join(', ')}]\n    limits: { max_leverage: ${deployable.limits.max_leverage}, drawdown_flatten_pct: ${deployable.limits.drawdown_flatten_pct}, daily_loss_pct: ${deployable.limits.daily_loss_pct} }\n`
  const copy = () => { navigator.clipboard?.writeText(yaml).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) }) }
  return (
    <div className="result">
      <div className="result-head">
        <Probe state="success" size={48} />
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
          <summary className="sub">Trades ({r.trades_sample.length} of {r.trades})</summary>
          <div className="tablewrap"><table className="mini">
            <thead><tr><th>When</th><th>Side</th><th className="num">Price</th><th className="num">Size</th><th>Why</th></tr></thead>
            <tbody>{r.trades_sample.map((t, i) => <tr key={i}><td>{day(t.ts)}</td><td className={t.side === 'buy' ? 'pos' : 'neg'}>{t.side}</td><td className="num">{Number(t.px).toLocaleString()}</td><td className="num">{Number(t.size).toFixed(4)}</td><td className="text sub">{t.reason}</td></tr>)}</tbody>
          </table></div>
        </details>
      )}
      {r.notes?.length > 0 && <ul className="notes">{r.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
      {deployable && (
        <div className="deploy">
          <div><b>Deploy as an agent</b><div className="sub">Inside hard limits: {deployable.limits.max_leverage}× max · stop at {deployable.limits.drawdown_flatten_pct}% drawdown · {deployable.limits.daily_loss_pct}% daily loss · {deployable.markets.join(', ')} only</div></div>
          <button onClick={copy}>{copied ? 'Copied' : 'Copy fleet.yaml entry'}</button>
        </div>
      )}
    </div>
  )
}

export default function Lab() {
  const [examples, setExamples] = useState([])
  const [msgs, setMsgs] = useState([{ role: 'ai', text: 'Ask a what-if. I turn it into a rule set, run it on price history, and show you what would have happened, fees included. Then you can deploy it inside hard limits.' }])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)

  useEffect(() => { fetch('/lab/examples').then((r) => r.json()).then((d) => setExamples(d.examples || [])).catch(() => {}) }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])

  async function ask(text) {
    const t = (text || q).trim()
    if (!t || busy) return
    setQ('')
    setMsgs((m) => [...m, { role: 'me', text: t }])
    setBusy(true)
    try {
      const r = await fetch('/lab/chat', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ message: t }) })
      const j = await r.json()
      setMsgs((m) => [...m, { role: 'ai', text: j.reply || j.detail || 'No reply', result: j.result, deployable: j.deployable, kind: j.kind }])
    } catch (e) {
      setMsgs((m) => [...m, { role: 'ai', text: `The Lab is unreachable (${e.message}).`, kind: 'error' }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="lab narrow">
      <div className="lab-head">
        <h1>Test an idea</h1>
        <p className="sub">What if I bought XMR every time a major company got hacked? What if I tailed this wallet? Say it like you'd say it to a friend. Or say it in the <a href="#/huddle/demo">group chat</a>, where friends back it and stake it.</p>
      </div>
      <div className="thread">
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">
              <div className={m.kind === 'error' ? 'neg' : ''}>{m.text}</div>
              {m.result && <Result r={m.result} deployable={m.deployable} />}
            </div>
          </div>
        ))}
        {busy && <div className="msg ai"><div className="bubble probe-status" role="status"><Probe state="thinking" size={100} /><div><b>Testing your idea…</b><p className="sub">Checking the strategy against the available price history.</p><SkelLines n={2} widths={['80%', '60%']} /></div></div></div>}
        <div ref={endRef} />
      </div>
      {examples.length > 0 && msgs.length < 3 && (
        <div className="examples">{examples.map((e) => <button key={e} onClick={() => ask(e)}>{e}</button>)}</div>
      )}
      <form className="ask" onSubmit={(e) => { e.preventDefault(); ask() }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="what if I…" disabled={busy} autoFocus aria-label="Your what-if" />
        <button className="primary" disabled={busy || !q.trim()}>Run</button>
      </form>
    </section>
  )
}
