import React, { useEffect, useState } from 'react'

// A leader writes a mandate, draws the lines, puts in the first money, and gets an invite link.

export default function NewLegion({ me, setMe }) {
  const [markets, setMarkets] = useState([])
  const [form, setForm] = useState({ name: '', mandate: '', leader: me || '', initial_deposit: 100, profit_share_pct: 10, max_leverage: 3, drawdown_flatten_pct: 10, daily_loss_pct: 4, max_notional_usd: 25000, allowed: [] })
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === 'number' ? Number(e.target.value) : e.target.value }))

  useEffect(() => { fetch('/v1/markets').then((r) => r.json()).then((d) => setMarkets(Object.keys(d.markets || {}))).catch(() => {}) }, [])
  useEffect(() => { if (me && !form.leader) setForm((f) => ({ ...f, leader: me })) }, [me])

  const toggle = (m) => setForm((f) => ({ ...f, allowed: f.allowed.includes(m) ? f.allowed.filter((x) => x !== m) : [...f.allowed, m] }))

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const body = {
        name: form.name, mandate: form.mandate, leader: form.leader.trim().toLowerCase(), initial_deposit: form.initial_deposit, profit_share_pct: form.profit_share_pct,
        limits: { max_leverage: form.max_leverage, drawdown_flatten_pct: form.drawdown_flatten_pct, daily_loss_pct: form.daily_loss_pct, max_notional_usd: form.max_notional_usd, allowed_markets: form.allowed.length ? form.allowed : undefined },
      }
      const r = await fetch('/orgs', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
      const j = await r.json()
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail))
      if (!me) setMe(body.leader)
      setDone(j)
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    const link = `${location.origin}/#/p/${done.slug}`
    return (
      <section className="one">
        <h1>{done.name} is open</h1>
        <p className="sub">Send the link to your friends. Your org key is below; it is the only thing that can add agents or change the mandate, and it is shown once.</p>
        <div className="card pad list">
          <div className="kv"><span>Invite link</span><span><a href={`#/p/${done.slug}`}>{link}</a></span></div>
          <div className="kv"><span>Org key</span><span style={{ wordBreak: 'break-all' }}>{done.org_key}</span></div>
          <div className="kv"><span>Pool</span><span>${done.pool_cash} from {done.depositors} depositor</span></div>
        </div>
        <div className="actions">
          <button className="primary" onClick={() => navigator.clipboard?.writeText(link)}>Copy invite link</button>
          <a className="btn" href={`#/p/${done.slug}`}>Open the legion</a>
        </div>
        <p className="sub">Next: give an agent a slice of the pool with <code>POST /orgs/{done.slug}/agents</code> (org key as bearer) or add it under <code>orgs:</code> in <code>fleet.yaml</code>.</p>
      </section>
    )
  }

  return (
    <section className="one">
      <div><h1>Start a legion</h1><p className="sub" style={{ marginTop: 8 }}>Write the mandate your friends are signing up for, draw the lines no agent can cross, put in the first money.</p></div>
      <form className="card pad form" onSubmit={submit}>
        <label>Name<input value={form.name} onChange={set('name')} placeholder="Lee's Semis Legion" required minLength={2} maxLength={64} /></label>
        <label>Your handle<input value={form.leader} onChange={set('leader')} placeholder="lee" required /></label>
        <label>Mandate<textarea value={form.mandate} onChange={set('mandate')} rows={3} placeholder="Memory and AI chips are mispriced vs demand. Trade NVDA and SP500 perps plus BTC as a hedge. Never above 3x. Stop everything at 12% drawdown." required minLength={10} maxLength={1000} /></label>
        <div className="grid4">
          <label>Max leverage<input type="number" min="1" max="50" step="0.5" value={form.max_leverage} onChange={set('max_leverage')} /></label>
          <label>Stop at drawdown %<input type="number" min="1" max="100" step="1" value={form.drawdown_flatten_pct} onChange={set('drawdown_flatten_pct')} /></label>
          <label>Daily loss %<input type="number" min="0.5" max="100" step="0.5" value={form.daily_loss_pct} onChange={set('daily_loss_pct')} /></label>
          <label>Max notional $<input type="number" min="100" step="100" value={form.max_notional_usd} onChange={set('max_notional_usd')} /></label>
        </div>
        <div>
          <div className="sub" style={{ marginBottom: 8 }}>Markets agents may touch (none selected = defaults)</div>
          <div className="chips pick">{markets.map((m) => <button type="button" key={m} className={form.allowed.includes(m) ? 'on' : ''} onClick={() => toggle(m)}>{m}</button>)}</div>
        </div>
        <div className="grid4">
          <label>Your first deposit $<input type="number" min="0" step="10" value={form.initial_deposit} onChange={set('initial_deposit')} /></label>
          <label>Your cut of profits %<input type="number" min="0" max="50" step="1" value={form.profit_share_pct} onChange={set('profit_share_pct')} /></label>
        </div>
        {err && <div className="err">{err}</div>}
        <div className="actions" style={{ margin: 0 }}><button className="primary" disabled={busy}>{busy ? 'Starting…' : 'Start the legion'}</button></div>
      </form>
    </section>
  )
}
