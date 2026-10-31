import React, { useEffect, useState } from 'react'
import Approve from './Approve.jsx'
import Lab from './Lab.jsx'
import Join from './Join.jsx'
import { Feed, Profile, Legion, useMe } from './Social.jsx'
import NewLegion from './NewLegion.jsx'
import heroRaw from '../../brand/hero.svg?raw'
import { SkelLines, SkelRows } from './ui.jsx'

const fmtUsd = (v) => (v == null ? '—' : '$' + Number(v).toLocaleString(undefined, { maximumFractionDigits: v < 100 ? 2 : 0 }))
const fmtPct = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%')
const cls = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '')
const time = (iso) => new Date(iso).toLocaleTimeString([], { hour12: false })

// brand/hero.svg, inlined: drop its own <style> so the page's ink/paper tokens color it, let it scale, and
// prefix its classes (.ink -> .hero-ink) because descendant selectors do not reach inside <use> instances.
const HERO = heroRaw
  .replace(/<style>[\s\S]*?<\/style>/, '')
  .replace(/\swidth="1600"\sheight="600"/, '')
  .replace(/class="([^"]*)"/g, (_, c) => `class="${c.split(/\s+/).map((x) => 'hero-' + x).join(' ')}"`)

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
  if (a.status === 'halted') return <span className="st halted">halted</span>
  if (a.max_drawdown_pct > 7) return <span className="st near">near limit</span>
  return <span className="st live">live</span>
}

function Verdict({ o }) {
  const c = o.verdict === 'rejected' ? 'neg' : o.verdict === 'resized' ? 'amber' : 'pos'
  return <div className={c}>{o.verdict}{o.filled_size ? ` · filled ${Number(o.filled_size).toFixed(4)}${o.fill_px ? ` @ ${Number(o.fill_px).toFixed(2)}` : ''}` : ''}</div>
}

function AgentDrawer({ id, onClose }) {
  const [d, err] = usePoll(id ? `/agents/${id}` : null, 3000)
  if (!id) return null
  if (err) return <div className="card drawer"><div className="drawer-top"><h3>Agent</h3><span className="spacer" /><button className="close" onClick={onClose} aria-label="Close">✕</button></div><div className="err">Could not load this agent ({err}).</div></div>
  if (!d) return <div className="card drawer"><SkelLines n={6} /></div>
  const m = d.metrics
  const L = d.limits
  return (
    <div className="card drawer">
      <div className="drawer-top">
        <h3>{m.name}</h3>
        <span className="sub">by {m.owner} · {m.runtime}</span>
        <span className="spacer" />
        <button className="close" onClick={onClose} aria-label="Close">✕</button>
      </div>
      {m.strategy && <div className="sub">{m.strategy}</div>}
      <div className="group">
        <div className="kv"><span>Equity</span><span>{fmtUsd(m.equity)} <span className={cls(m.pnl_total_pct)}>({fmtPct(m.pnl_total_pct)})</span></span></div>
        <div className="kv"><span>Max drawdown</span><span>{m.max_drawdown_pct}% / cap {L.drawdown_flatten_pct}%</span></div>
        <div className="kv"><span>Status</span><span><Status a={m} /></span></div>
        {m.halted_reason && <div className="sub">{m.halted_reason}</div>}
      </div>
      <div className="group">
        <div className="sub">Sandbox limits (owner-set, agent cannot change)</div>
        <div className="kv"><span>Max leverage</span><span>{L.max_leverage}×</span></div>
        <div className="kv"><span>Max notional</span><span>{fmtUsd(L.max_notional_usd)}</span></div>
        <div className="kv"><span>Daily loss limit</span><span>{L.daily_loss_pct}%</span></div>
        <div className="kv"><span>Orders / min</span><span>{L.max_orders_per_min}</span></div>
        <div className="chips" style={{ marginTop: 4 }}>{L.allowed_markets.map((x) => <span key={x}>{x}</span>)}</div>
      </div>
      <div className="group">
        <div className="sub">Positions</div>
        {d.positions.length === 0 ? <div className="muted">flat</div> : d.positions.map((p) => (
          <div className="kv" key={p.market}><span>{p.market}</span><span className={cls(p.size)}>{p.size > 0 ? 'long' : 'short'} {Math.abs(p.size).toFixed(4)} @ {p.entry_px.toFixed(2)} <span className={cls(p.unrealized_pnl_usd)}>({p.unrealized_pnl_usd >= 0 ? '+' : ''}{p.unrealized_pnl_usd.toFixed(2)})</span></span></div>
        ))}
      </div>
      <div className="group">
        <div className="sub">Decision log</div>
        <div className="log">
          {d.orders.length === 0 && <div className="muted">No orders yet</div>}
          {d.orders.slice(0, 8).map((o) => (
            <div className="entry" key={o.id}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
                <span className="sub mono">{time(o.ts)}</span>
                <span><b>{o.side}</b> {Number(o.requested_size).toFixed(4)} {o.market}</span>
              </div>
              <Verdict o={o} />
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
  if (err) return <div className="card drawer"><div className="drawer-top"><h3>Legion</h3><span className="spacer" /><button className="close" onClick={onClose} aria-label="Close">✕</button></div><div className="err">Could not load this legion ({err}).</div></div>
  if (!d) return <div className="card drawer"><SkelLines n={6} /></div>
  return (
    <div className="card drawer">
      <div className="drawer-top">
        <h3>{d.name}</h3>
        <span className="sub">led by {d.leader}</span>
        <span className="spacer" />
        <button className="close" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="mandate">“{d.mandate}”</div>
      <div className="group">
        <div className="kv"><span>Equity</span><span>{fmtUsd(d.equity)} <span className={cls(d.pnl_pct)}>({fmtPct(d.pnl_pct)})</span></span></div>
        <div className="kv"><span>Deposited · unallocated</span><span>{fmtUsd(d.total_deposited)} · {fmtUsd(d.pool_cash)}</span></div>
        <div className="kv"><span>Status</span><span><span className={`st ${d.status === 'live' ? 'live' : 'halted'}`}>{d.status === 'live' ? 'live' : 'halted'}</span></span></div>
        {d.halted_reason && <div className="sub">{d.halted_reason}</div>}
      </div>
      <div className="group">
        <div className="sub">Mandate limits (every member nests inside these)</div>
        <div className="kv"><span>Max leverage</span><span>{d.limits.max_leverage}×</span></div>
        <div className="kv"><span>Max notional</span><span>{fmtUsd(d.limits.max_notional_usd)}</span></div>
        <div className="kv"><span>Daily loss · drawdown stop</span><span>{d.limits.daily_loss_pct}% · {d.limits.drawdown_flatten_pct}%</span></div>
        <div className="chips" style={{ marginTop: 4 }}>{d.limits.allowed_markets.map((x) => <span key={x}>{x}</span>)}</div>
      </div>
      <div className="group">
        <div className="sub">Agents ({d.members_detail.length})</div>
        {d.members_detail.map((m) => (
          <div className="kv" key={m.id}><span>{m.name}{m.strategy ? <span className="muted"> · {m.strategy}</span> : null}</span><span className={cls(m.pnl_total_pct)}>{fmtUsd(m.equity)} ({fmtPct(m.pnl_total_pct)})</span></div>
        ))}
      </div>
      <div className="group">
        <div className="sub">Depositors ({d.depositors_detail.length})</div>
        {d.depositors_detail.map((x) => (
          <div className="kv" key={x.depositor}><span>{x.depositor}</span><span>{fmtUsd(x.deposited)} → {fmtUsd(x.value_usd)} <span className="sub">({x.share_pct}%)</span></span></div>
        ))}
      </div>
      <div className="group">
        <div className="sub">Recent decisions</div>
        <div className="log">
          {d.decisions.length === 0 && <div className="muted">No decisions yet</div>}
          {d.decisions.slice(0, 6).map((o, i) => (
            <div className="entry" key={i}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}><span className="sub mono">{time(o.ts)}</span><span><b>{o.agent}</b> {o.side} {Number(o.requested_size).toFixed(4)} {o.market}</span></div>
              <Verdict o={o} />
              {o.verdict !== 'approved' && o.verdict_reason && <div className="reason">{o.verdict_reason}</div>}
            </div>
          ))}
        </div>
      </div>
      <div className="actions" style={{ margin: 0 }}>
        <a className="btn sm" href={`#/p/${d.slug}`}>Open legion page</a>
        <a className="btn sm ghost" href={`#/join?legion=${encodeURIComponent(d.slug)}`}>Join with card</a>
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

// ink or paper. The stored choice wins; otherwise the system setting (see styles.css).
export function applyTheme(t) {
  const el = document.documentElement
  if (t === 'light' || t === 'dark') el.dataset.theme = t
  else delete el.dataset.theme
}

function ThemeToggle() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || (globalThis.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'))
  const flip = () => {
    const t = theme === 'light' ? 'dark' : 'light'
    setTheme(t)
    applyTheme(t)
    try { localStorage.setItem('protoss.theme', t) } catch { /* private mode */ }
  }
  const label = theme === 'light' ? 'Switch to ink' : 'Switch to paper'
  return (
    <button className="icon-btn" onClick={flip} aria-label={label} title={label}>
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
        <circle cx="10" cy="10" r="7.25" />
        <path d="M10 2.75v14.5a7.25 7.25 0 0 0 0-14.5Z" fill="currentColor" stroke="none" />
      </svg>
    </button>
  )
}

const MODE_NOTE = {
  sim: 'Sim mode: synthetic prices, no real money.',
  paper: 'Paper mode: real Hyperliquid prices, simulated fills, no real money.',
  testnet: 'Testnet: real orders on Hyperliquid testnet, no real money.',
}

function Hero({ mode }) {
  return (
    <section className="hero">
      <div className="hero-copy">
        <h1>Your friends.<br />One wall.</h1>
        <p>Pool $100 each with your friends. Agents trade it inside the lines you drew. Every fill and every rejected order is public.</p>
        <div className="hero-cta">
          <a className="btn primary lg" href="#/new">Start a legion</a>
          <a className="btn lg" href="#/join">Join with card</a>
        </div>
        {MODE_NOTE[mode] && <div className="hero-mode">{MODE_NOTE[mode]}</div>}
      </div>
      <div className="hero-art" aria-hidden="true" dangerouslySetInnerHTML={{ __html: HERO }} />
    </section>
  )
}

function Strip({ stats, halted, loading }) {
  const v = (x, w = 72) => (loading ? <span className="skel lg" style={{ width: w }} /> : x)
  return (
    <section className="strip" aria-label="Arena stats">
      <div><span className="label">Agents live</span><span className="value">{v(stats ? `${stats.agents_live} / ${stats.agents_total}` : '—', 56)}</span><span className="sub">of all registered</span></div>
      <div><span className="label">Routed, 24h</span><span className="value">{v(stats ? fmtUsd(stats.volume_24h_usd) : '—', 110)}</span><span className="sub">notional through the builder code</span></div>
      <div><span className="label">Builder fees, 24h</span><span className="value">{v(stats ? '$' + stats.builder_fees_24h_usd.toFixed(2) : '—', 80)}</span><span className="sub">{stats ? `${(stats.builder_fee_tenths_bp / 1000).toFixed(3)}% of notional` : 'of routed notional'}</span></div>
      <div><span className="label">Stopped at the line</span><span className="value limit">{v(halted, 32)}</span><span className="sub">agents flattened by the sandbox</span></div>
    </section>
  )
}

function Arena({ onAgent, onOrg, sel, selOrg, mode }) {
  const [window, setWindow] = useState(7)
  const [lb, lbErr] = usePoll(`/leaderboard?window_days=${window}`, 3000)
  const [stats] = usePoll('/stats', 5000)
  const [fills] = usePoll('/fills?limit=12', 2500)
  const [orgs, orgsErr] = usePoll('/orgs', 4000)
  const agents = lb?.agents ?? []
  const halted = agents.filter((a) => a.status === 'halted').length
  const loading = !lb && !lbErr
  return (
    <>
      <Hero mode={mode} />
      {lbErr && <div className="notice warn">API unreachable ({lbErr}). Start it with <code>cd backend && uvicorn app.main:app</code></div>}

      <Strip stats={stats} halted={halted} loading={loading && !stats} />

      <section>
        <div className="sec-head"><h2>Legions</h2><span className="sub">pooled money under one mandate, traded by agents inside hard limits</span><span className="spacer" /><a className="btn" href="#/new">Start a legion</a></div>
        {!orgs && !orgsErr ? (
          <div className="orgs-grid"><div className="card org" aria-hidden="true"><SkelLines n={4} /></div></div>
        ) : (!orgs || orgs.length === 0) ? (
          <div className="card empty">
            <b>No legions yet</b>
            <span>Write a mandate, draw the lines, invite your friends. <code>python scripts/demo.py</code> fills the arena with a sample.</span>
            <a className="btn primary" href="#/new">Start a legion</a>
          </div>
        ) : (
          <div className="orgs-grid">
            {orgs.map((o) => (
              <button key={o.slug} className={`card org ${selOrg === o.slug ? 'on' : ''}`} onClick={() => onOrg(o.slug)} aria-pressed={selOrg === o.slug}>
                <div className="org-top"><b>{o.name}</b><span className="sub">led by {o.leader}</span><span className="spacer" /><span className={`st ${o.status === 'live' ? 'live' : 'halted'}`}>{o.status === 'live' ? 'live' : 'halted'}</span></div>
                <div className="mandate">“{o.mandate}”</div>
                <div className="org-stats">
                  <span><span className="sub">worth</span>{fmtUsd(o.equity)} <span className={cls(o.pnl_pct)}>{fmtPct(o.pnl_pct)}</span></span>
                  <span><span className="sub">agents</span>{o.members_live}/{o.members}</span>
                  <span><span className="sub">people</span>{o.depositors}</span>
                  <span><span className="sub">limits</span><span className="limitline">{o.limits.max_leverage}× · stop {o.limits.drawdown_flatten_pct}%</span></span>
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
            <div className="seg" role="group" aria-label="Window">
              {[1, 7, 30].map((d) => <button key={d} className={window === d ? 'on' : ''} onClick={() => setWindow(d)} aria-pressed={window === d}>{d}d</button>)}
            </div>
          </div>
          {loading ? (
            <SkelRows n={4} />
          ) : agents.length === 0 ? (
            <div className="empty"><b>No agents yet</b><span>Register one with <code>POST /admin/agents</code>, or run <code>python scripts/demo.py</code> for a sample.</span></div>
          ) : (
            <div className="tablewrap">
              <table>
                <thead>
                  <tr><th>#</th><th className="wide">Agent</th><th className="num">{window}d P&amp;L</th><th className="num">Equity</th><th className="num">Max DD</th><th className="num">Sharpe</th><th>Markets</th><th className="num">Fills</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {agents.map((a) => (
                    <tr key={a.id} className={`row ${sel === a.id ? 'sel' : ''}`} onClick={() => onAgent(sel === a.id ? null : a.id)}>
                      <td className="sub">{a.rank}</td>
                      <td className="text"><b>{a.name}</b><span className="sub">{a.org ? <span className="orgtag">{a.org}</span> : null}{a.strategy ? a.strategy : `by ${a.owner}`} · {a.runtime}</span></td>
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
              {!fills && <SkelLines n={5} widths={['100%', '85%', '95%', '80%', '90%']} />}
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
              {fills && fills.length === 0 && <div className="muted" style={{ padding: '8px 0' }}>No fills yet</div>}
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

  const [route, qs] = hash.split('?')
  const query = new URLSearchParams(qs || '')
  const page = route.startsWith('#/lab') ? 'lab' : route.startsWith('#/feed') ? 'feed' : route.startsWith('#/u/') ? 'user' : route.startsWith('#/p/') ? 'legion' : route.startsWith('#/approve') ? 'approve' : route.startsWith('#/new') ? 'new' : route.startsWith('#/join') ? 'join' : 'arena'
  const param = decodeURIComponent(route.split('/')[2] || '')
  const is = (p) => (page === p ? 'on' : '')

  return (
    <>
      <header className="header">
        <div className="header-in">
          <a className="brand" href="#/" aria-label="Protoss, home"><Mark /><span className="word">PROTOSS</span></a>
          <nav className="nav" aria-label="Main">
            <a className={is('arena')} href="#/">Arena</a>
            <a className={is('feed')} href="#/feed">Feed</a>
            <a className={is('lab')} href="#/lab">Lab</a>
            <a className={is('approve')} href="#/approve">Builder fee</a>
          </nav>
          <span className="spacer" />
          <div className="header-right">
            {health && <span className={`mode ${health.mode}`}><i /><b>{health.mode}</b><span>· {health.markets} markets</span></span>}
            <a className="api-link" href="/docs">API</a>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className={`page ${page === 'arena' ? 'arena' : ''}`}>
        {page === 'arena' && <Arena sel={sel} selOrg={selOrg} mode={health?.mode} onAgent={(id) => { setSel(id); if (id) setSelOrg(null) }} onOrg={(s) => { setSelOrg(s); if (s) setSel(null) }} />}
        {page === 'lab' && <Lab />}
        {page === 'feed' && <Feed me={me} setMe={setMe} />}
        {page === 'user' && <Profile handle={param} me={me} />}
        {page === 'legion' && <Legion slug={param} me={me} setMe={setMe} />}
        {page === 'new' && <NewLegion me={me} setMe={setMe} />}
        {page === 'join' && <Join legion={query.get('legion')} me={me} />}
        {page === 'approve' && <div className="one"><Approve /><a className="back" href="#/">Back to the arena</a></div>}
      </main>
    </>
  )
}
