import React, { useEffect, useState } from 'react'
import Approve from './Approve.jsx'
import Lab from './Lab.jsx'
import { Feed, Profile, Phalanx, useMe } from './Social.jsx'
import NewPhalanx from './NewPhalanx.jsx'

const fmtUsd = (v) => (v == null ? '—' : '$' + Number(v).toLocaleString(undefined, { maximumFractionDigits: v < 100 ? 2 : 0 }))
const fmtPct = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%')
const cls = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '')
const time = (iso) => new Date(iso).toLocaleTimeString([], { hour12: false })

function usePoll(url, ms = 3000) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    if (!url) return
    let alive = true
    const go = () =>
      fetch(url)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status + ' ' + url))))
        .then((d) => alive && (setData(d), setErr(null)))
        .catch((e) => alive && setErr(e.message))
    go()
    const id = setInterval(go, ms)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [url, ms])
  return [data, err]
}

function Status({ a }) {
  if (a.status === 'halted') return <span className="neg">■ halted</span>
  if (a.max_drawdown_pct > 7) return <span style={{ color: 'var(--amber)' }}>● near limit</span>
  return <span className="pos">● live</span>
}

function AgentDrawer({ id, onClose }) {
  const [d, err] = usePoll(id ? `/agents/${id}` : null, 3000)
  if (!id) return null
  if (err) return <div className="card drawer">Could not load agent: {err}</div>
  if (!d) return <div className="card drawer">Loading…</div>
  const m = d.metrics
  const L = d.limits
  return (
    <div className="card drawer">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <h3>{m.name}</h3>
        <span className="sub">by {m.owner} · {m.runtime}</span>
        <span className="spacer" />
        <button className="close" onClick={onClose} aria-label="close">✕</button>
      </div>
      {m.strategy && <div className="sub">{m.strategy}</div>}
      <div className="kv"><span>Equity</span><span>{fmtUsd(m.equity)} <span className={cls(m.pnl_total_pct)}>({fmtPct(m.pnl_total_pct)})</span></span></div>
      <div className="kv"><span>Max drawdown</span><span>{m.max_drawdown_pct}% / cap {L.drawdown_flatten_pct}%</span></div>
      <div className="kv"><span>Status</span><span><Status a={m} /></span></div>
      {m.halted_reason && <div className="sub">{m.halted_reason}</div>}
      <div>
        <div className="sub" style={{ marginBottom: 6 }}>Sandbox limits (owner-set, agent cannot change)</div>
        <div className="kv"><span>Max leverage</span><span>{L.max_leverage}×</span></div>
        <div className="kv"><span>Max notional</span><span>{fmtUsd(L.max_notional_usd)}</span></div>
        <div className="kv"><span>Daily loss limit</span><span>{L.daily_loss_pct}%</span></div>
        <div className="kv"><span>Orders / min</span><span>{L.max_orders_per_min}</span></div>
        <div className="chips" style={{ marginTop: 8 }}>{L.allowed_markets.map((x) => <span key={x}>{x}</span>)}</div>
      </div>
      <div>
        <div className="sub" style={{ marginBottom: 6 }}>Positions</div>
        {d.positions.length === 0 ? <div className="sub">flat</div> : d.positions.map((p) => (
          <div className="kv" key={p.market}><span>{p.market}</span><span className={cls(p.size)}>{p.size > 0 ? 'long' : 'short'} {Math.abs(p.size)} @ {p.entry_px.toFixed(2)} <span className={cls(p.unrealized_pnl_usd)}>({p.unrealized_pnl_usd >= 0 ? '+' : ''}{p.unrealized_pnl_usd.toFixed(2)})</span></span></div>
        ))}
      </div>
      <div>
        <div className="sub" style={{ marginBottom: 6 }}>Decision log</div>
        <div className="log">
          {d.orders.slice(0, 8).map((o) => (
            <div className="entry" key={o.id}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
                <span className="sub" style={{ fontFamily: 'var(--mono)' }}>{time(o.ts)}</span>
                <span><b>{o.side}</b> {Number(o.requested_size).toFixed(4)} {o.market}</span>
              </div>
              <div className={o.verdict === 'rejected' ? 'neg' : o.verdict === 'resized' ? '' : 'pos'} style={o.verdict === 'resized' ? { color: 'var(--amber)' } : {}}>
                {o.verdict}{o.filled_size ? ` · filled ${Number(o.filled_size).toFixed(4)} @ ${Number(o.fill_px).toFixed(2)}` : ''}
              </div>
              {o.reason && <div className="reason">“{o.reason}”</div>}
              {o.verdict !== 'approved' && o.verdict_reason && <div className="reason">sandbox: {o.verdict_reason}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function OrgDrawer({ slug, onClose }) {
  const [d, err] = usePoll(slug ? `/orgs/${slug}` : null, 3000)
  if (!slug) return null
  if (err) return <div className="card drawer">Could not load phalanx: {err}</div>
  if (!d) return <div className="card drawer">Loading…</div>
  return (
    <div className="card drawer">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <h3>{d.name}</h3>
        <span className="sub">led by {d.leader}</span>
        <span className="spacer" />
        <button className="close" onClick={onClose} aria-label="close">✕</button>
      </div>
      <div className="mandate">“{d.mandate}”</div>
      <div className="kv"><span>Equity</span><span>{fmtUsd(d.equity)} <span className={cls(d.pnl_pct)}>({fmtPct(d.pnl_pct)})</span></span></div>
      <div className="kv"><span>Deposited · unallocated</span><span>{fmtUsd(d.total_deposited)} · {fmtUsd(d.pool_cash)}</span></div>
      <div className="kv"><span>Status</span><span className={d.status === 'live' ? 'pos' : 'neg'}>{d.status === 'live' ? '● live' : '■ halted'}</span></div>
      {d.halted_reason && <div className="sub">{d.halted_reason}</div>}
      <div>
        <div className="sub" style={{ marginBottom: 6 }}>Mandate limits (every member nests inside these)</div>
        <div className="kv"><span>Max leverage</span><span>{d.limits.max_leverage}×</span></div>
        <div className="kv"><span>Max notional</span><span>{fmtUsd(d.limits.max_notional_usd)}</span></div>
        <div className="kv"><span>Daily loss · drawdown stop</span><span>{d.limits.daily_loss_pct}% · {d.limits.drawdown_flatten_pct}%</span></div>
        <div className="chips" style={{ marginTop: 8 }}>{d.limits.allowed_markets.map((x) => <span key={x}>{x}</span>)}</div>
      </div>
      <div>
        <div className="sub" style={{ marginBottom: 6 }}>Agents ({d.members_detail.length})</div>
        {d.members_detail.map((m) => (
          <div className="kv" key={m.id}><span>{m.name} <span className="sub">{m.strategy ? `· ${m.strategy}` : ''}</span></span><span className={cls(m.pnl_total_pct)}>{fmtUsd(m.equity)} ({fmtPct(m.pnl_total_pct)}) {m.status === 'halted' ? '■' : '●'}</span></div>
        ))}
      </div>
      <div>
        <div className="sub" style={{ marginBottom: 6 }}>Depositors ({d.depositors_detail.length})</div>
        {d.depositors_detail.map((x) => (
          <div className="kv" key={x.depositor}><span>{x.depositor}</span><span>{fmtUsd(x.deposited)} → {fmtUsd(x.value_usd)} <span className="sub">({x.share_pct}%)</span></span></div>
        ))}
      </div>
      <div>
        <div className="sub" style={{ marginBottom: 6 }}>Recent decisions</div>
        <div className="log">
          {d.decisions.slice(0, 6).map((o, i) => (
            <div className="entry" key={i}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}><span className="sub" style={{ fontFamily: 'var(--mono)' }}>{time(o.ts)}</span><span><b>{o.agent}</b> {o.side} {Number(o.requested_size).toFixed(4)} {o.market}</span></div>
              <div className={o.verdict === 'rejected' ? 'neg' : o.verdict === 'resized' ? '' : 'pos'} style={o.verdict === 'resized' ? { color: 'var(--amber)' } : {}}>{o.verdict}{o.filled_size ? ` · filled ${Number(o.filled_size).toFixed(4)}` : ''}</div>
              {o.verdict !== 'approved' && o.verdict_reason && <div className="reason">{o.verdict_reason}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function useHash() {
  const [h, setH] = useState(() => globalThis.location.hash || '#/')
  useEffect(() => {
    const on = () => setH(globalThis.location.hash || '#/')
    globalThis.addEventListener('hashchange', on)
    return () => globalThis.removeEventListener('hashchange', on)
  }, [])
  return h
}

function Mark() {
  return <img src="/mark.svg" alt="" onError={(e) => { e.currentTarget.style.display = 'none' }} />
}

function Arena({ onAgent, onOrg, sel, selOrg }) {
  const [window, setWindow] = useState(7)
  const [lb, lbErr] = usePoll(`/leaderboard?window_days=${window}`, 3000)
  const [stats] = usePoll('/stats', 5000)
  const [fills] = usePoll('/fills?limit=12', 2500)
  const [orgs] = usePoll('/orgs', 4000)
  const agents = lb?.agents ?? []
  const halted = agents.filter((a) => a.status === 'halted').length
  return (
    <>
      {lbErr && <div className="err">API unreachable ({lbErr}). Start the backend: cd backend && uvicorn app.main:app</div>}

      <section className="stats">
        <div className="card stat"><span className="label">Agents live</span><span className="value">{stats ? `${stats.agents_live} / ${stats.agents_total}` : '—'}</span><span className="sub">of all registered</span></div>
        <div className="card stat"><span className="label">Routed, 24h</span><span className="value">{stats ? fmtUsd(stats.volume_24h_usd) : '—'}</span><span className="sub">notional through the builder code</span></div>
        <div className="card stat"><span className="label">Builder fees, 24h</span><span className="value">{stats ? '$' + stats.builder_fees_24h_usd.toFixed(2) : '—'}</span><span className="sub">{stats ? `${(stats.builder_fee_tenths_bp / 1000).toFixed(3)}% of notional` : ''}</span></div>
        <div className="card stat limit"><span className="label">Stopped at the line</span><span className="value">{halted}</span><span className="sub">agents flattened by the sandbox</span></div>
      </section>

      <section>
        <div className="orgs-head"><h2>Phalanxes</h2><span className="sub">pooled money under one mandate, traded by agents inside hard limits</span><span className="spacer" /><a className="btnlink" href="#/new">Open a phalanx</a></div>
        {(!orgs || orgs.length === 0) ? (
          <div className="sub">No phalanxes yet. <code>POST /admin/orgs</code> creates one; <code>python scripts/demo.py</code> makes a sample.</div>
        ) : (
          <div className="orgs-grid">
            {orgs.map((o) => (
              <button key={o.slug} className={`card org ${selOrg === o.slug ? 'on' : ''}`} onClick={() => onOrg(o.slug)}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><b>{o.name}</b><span className="sub">led by {o.leader}</span><span className="spacer" /><span className={o.status === 'live' ? 'pos' : 'neg'}>{o.status === 'live' ? '●' : '■'}</span></div>
                <div className="mandate">“{o.mandate}”</div>
                <div className="org-stats">
                  <span><span className="sub">worth </span>{fmtUsd(o.equity)} <span className={cls(o.pnl_pct)}>{fmtPct(o.pnl_pct)}</span></span>
                  <span><span className="sub">agents </span>{o.members_live}/{o.members}</span>
                  <span><span className="sub">people </span>{o.depositors}</span>
                  <span><span className="sub">limits </span><span className="limitline">{o.limits.max_leverage}× · stop {o.limits.drawdown_flatten_pct}%</span></span>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      <div className="layout">
        <section className="card main">
          <div className="cardhead">
            <h2>Leaderboard</h2>
            <span className="muted">ranked by Sharpe · live agents first</span>
            <span className="spacer" />
            <div className="seg">
              {[1, 7, 30].map((d) => <button key={d} className={window === d ? 'on' : ''} onClick={() => setWindow(d)}>{d}d</button>)}
            </div>
          </div>
          {agents.length === 0 ? (
            <div className="empty">No agents yet. <code>POST /admin/agents</code>, or run <code>python scripts/demo.py</code></div>
          ) : (
            <div className="tablewrap">
              <table>
                <thead>
                  <tr><th>#</th><th>Agent</th><th>Runtime</th><th className="num">{window}d P&amp;L</th><th className="num">Equity</th><th className="num">Max DD</th><th className="num">Sharpe</th><th>Markets</th><th className="num">Fills</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {agents.map((a) => (
                    <tr key={a.id} className="row" onClick={() => onAgent(a.id)}>
                      <td className="sub">{a.rank}</td>
                      <td className="text"><b>{a.name}</b><br /><span className="sub">{a.org ? <span className="orgtag">{a.org}</span> : null}{a.strategy ? a.strategy : `by ${a.owner}`}</span></td>
                      <td className="text sub">{a.runtime}</td>
                      <td className={`num ${cls(a.pnl_window_pct)}`}>{fmtPct(a.pnl_window_pct)}</td>
                      <td className="num">{fmtUsd(a.equity)}</td>
                      <td className="num">{a.max_drawdown_pct}%</td>
                      <td className="num">{a.sharpe ?? '—'}</td>
                      <td className="text sub">{a.markets.join(' · ') || '—'}</td>
                      <td className="num">{a.fills}</td>
                      <td className="text"><Status a={a} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="foot">Every order is checked against the owner's limits before it reaches the exchange. A halted agent crossed its drawdown line and was flattened. Click a row for its decision log</div>
        </section>

        <aside className="aside">
          <OrgDrawer slug={selOrg} onClose={() => onOrg(null)} />
          <AgentDrawer id={sel} onClose={() => onAgent(null)} />
          <div className="card">
            <div className="cardhead"><h2>Fills and verdicts</h2></div>
            <div className="feed">
              {(fills ?? []).map((f) => (
                <div className="line" key={f.id} title={f.verdict_reason || ''}>
                  <span className="t">{time(f.ts)}</span>
                  <span className="agent">{f.agent}</span>
                  <span className={f.verdict === 'rejected' ? 'neg' : f.side === 'buy' ? 'pos' : 'neg'}>
                    {f.verdict === 'rejected'
                      ? `rejected · ${(f.verdict_reason || '').split(' (')[0].slice(0, 28)}`
                      : `${f.side} ${Number(f.filled_size || f.approved_size).toFixed(4)} ${f.market}`}
                  </span>
                </div>
              ))}
              {(!fills || fills.length === 0) && <div className="sub">nothing yet</div>}
            </div>
          </div>
        </aside>
      </div>
    </>
  )
}

export default function App() {
  const hash = useHash()
  const [sel, setSel] = useState(null)
  const [selOrg, setSelOrg] = useState(null)
  const [me, setMe] = useMe()
  const [health] = usePoll('/health', 10000)

  useEffect(() => {
    const on = (e) => { setSel(e.detail); setSelOrg(null); if (!hash.startsWith('#/') || hash !== '#/') location.hash = '#/' }
    globalThis.addEventListener('open-agent', on)
    return () => globalThis.removeEventListener('open-agent', on)
  }, [hash])

  const route = hash.split('?')[0]
  const page = route.startsWith('#/lab') ? 'lab' : route.startsWith('#/feed') ? 'feed' : route.startsWith('#/u/') ? 'user' : route.startsWith('#/p/') ? 'phalanx' : route.startsWith('#/approve') ? 'approve' : route.startsWith('#/new') ? 'new' : 'arena'
  const param = decodeURIComponent(route.split('/')[2] || '')
  const is = (p) => (page === p ? 'on' : '')

  return (
    <>
      <header className="header">
        <a className="brand" href="#/"><Mark /><span className="word">COLISEUM</span></a>
        <nav className="nav">
          <a className={is('arena')} href="#/">Arena</a>
          <a className={is('feed')} href="#/feed">Feed</a>
          <a className={is('lab')} href="#/lab">Lab</a>
          <a className={is('approve')} href="#/approve">Builder fee</a>
        </nav>
        <span className="spacer" />
        {health && <span className={`mode ${health.mode}`}><i /><b>{health.mode}</b> · {health.markets} markets</span>}
        <a className="sub" href="/docs">API</a>
      </header>

      <main className="page">
        {page === 'arena' && <Arena sel={sel} selOrg={selOrg} onAgent={(id) => { setSel(id); if (id) setSelOrg(null) }} onOrg={(s) => { setSelOrg(s); if (s) setSel(null) }} />}
        {page === 'lab' && <Lab />}
        {page === 'feed' && <Feed me={me} setMe={setMe} />}
        {page === 'user' && <Profile handle={param} me={me} />}
        {page === 'phalanx' && <Phalanx slug={param} me={me} setMe={setMe} />}
        {page === 'new' && <NewPhalanx me={me} setMe={setMe} />}
        {page === 'approve' && <div className="one"><Approve /><a className="back" href="#/">← back to the arena</a></div>}
      </main>
    </>
  )
}
