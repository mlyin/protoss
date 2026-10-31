import React, { useEffect, useState } from 'react'

// Social layer: the public feed, a person's page, and a legion's join page.

const fmtUsd = (v) => (v == null ? '—' : '$' + Number(v).toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) < 100 ? 2 : 0 }))
const fmtPct = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%')
const cls = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '')
const when = (iso) => { const d = new Date(iso); const s = (Date.now() - d) / 1000; return s < 60 ? 'now' : s < 3600 ? `${Math.floor(s / 60)}m` : s < 86400 ? `${Math.floor(s / 3600)}h` : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) }

export function useMe() {
  const [me, setMe] = useState(() => { try { return localStorage.getItem('coliseum.me') || '' } catch { return '' } })
  const set = (h) => { setMe(h); try { localStorage.setItem('coliseum.me', h) } catch { /* private mode */ } }
  return [me, set]
}

function usePoll(url, ms = 4000) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    if (!url) return
    let alive = true
    const go = () => fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status)))).then((d) => alive && (setData(d), setErr(null))).catch((e) => alive && setErr(e.message))
    go(); const id = setInterval(go, ms)
    return () => { alive = false; clearInterval(id) }
  }, [url, ms])
  return [data, err]
}

const ICON = { fill: '●', reject: '✕', resize: '≈', halt: '■', deposit: '+', new_agent: '↗', new_org: '⌂', follow: '→' }

export function FollowButton({ me, type, id, following, onChange }) {
  const [busy, setBusy] = useState(false)
  if (!me) return null
  const on = following?.some((f) => f.type === type && f.id === id)
  const go = async () => {
    setBusy(true)
    await fetch('/social/follow', { method: on ? 'DELETE' : 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ handle: me, target_type: type, target_id: id }) })
    setBusy(false); onChange?.()
  }
  return <button className={`follow ${on ? 'on' : ''}`} disabled={busy} onClick={(e) => { e.stopPropagation(); go() }}>{on ? 'Following' : 'Follow'}</button>
}

export function WhoAmI({ me, setMe }) {
  const [v, setV] = useState(me)
  return (
    <form className="whoami" onSubmit={(e) => { e.preventDefault(); setMe(v.trim().toLowerCase()) }}>
      <span className="sub">you are</span>
      <input value={v} onChange={(e) => setV(e.target.value)} placeholder="handle" />
      <button>{me ? 'switch' : 'set'}</button>
    </form>
  )
}

export function Feed({ me, setMe }) {
  const [mine, setMine] = useState(false)
  const [items, err] = usePoll(`/feed?limit=80${mine && me ? `&handle=${encodeURIComponent(me)}` : ''}`, 3000)
  const [prof] = usePoll(me ? `/u/${me}` : null, 8000)
  const following = prof?.following || []
  return (
    <section className="social">
      <div className="social-head">
        <h1>Feed</h1>
        <div className="seg"><button className={!mine ? 'on' : ''} onClick={() => setMine(false)}>everyone</button><button className={mine ? 'on' : ''} onClick={() => setMine(true)} disabled={!me}>following</button></div>
        <span className="spacer" />
        <WhoAmI me={me} setMe={setMe} />
      </div>
      {err && <div className="err">feed unreachable ({err})</div>}
      <div className="stream">
        {(items || []).map((i, k) => (
          <div className={`item ${i.kind}`} key={k}>
            <span className="ic">{ICON[i.kind] || '·'}</span>
            <div className="body">
              <div className="text">
                {i.agent_id ? <a href={`#/`} onClick={(e) => { e.preventDefault(); window.dispatchEvent(new CustomEvent('open-agent', { detail: i.agent_id })) }}><b>{i.actor}</b></a> : <a href={`#/u/${i.actor}`}><b>{i.actor}</b></a>}
                {' '}<span>{i.text.replace(new RegExp('^' + i.actor + ' '), '')}</span>
              </div>
              <div className="meta sub">{when(i.ts)}{i.org_slug && <> · <a href={`#/p/${i.org_slug}`}>{i.org_slug}</a></>}{i.market && <> · {i.market}</>}</div>
            </div>
            {i.agent_id && <FollowButton me={me} type="agent" id={i.agent_id} following={following} />}
            {!i.agent_id && i.org_slug && <FollowButton me={me} type="org" id={i.org_slug} following={following} />}
          </div>
        ))}
        {items && items.length === 0 && <div className="sub" style={{ padding: 16 }}>{mine ? 'Nothing from the people and legions you follow yet.' : 'Quiet arena.'}</div>}
      </div>
    </section>
  )
}

export function Profile({ handle, me }) {
  const [p, err] = usePoll(`/u/${handle}`, 5000)
  const [meP] = usePoll(me ? `/u/${me}` : null, 8000)
  if (err) return <section className="social"><div className="err">No one called {handle} here yet.</div></section>
  if (!p) return <section className="social"><div className="sub" style={{ padding: 16 }}>loading…</div></section>
  const pnl = p.total_deposited ? ((p.total_value_usd - p.total_deposited) / p.total_deposited) * 100 : null
  return (
    <section className="social">
      <div className="social-head">
        <div className="avatar">{handle.slice(0, 1).toUpperCase()}</div>
        <div><h1>{p.display_name}</h1><div className="sub">@{handle}{p.bio ? ` · ${p.bio}` : ''} · {p.followers} followers</div></div>
        <span className="spacer" />
        {me && me !== handle && <FollowButton me={me} type="user" id={handle} following={meP?.following} />}
      </div>
      <div className="statrow">
        <div><span className="label">Staked</span><span className="value">{fmtUsd(p.total_deposited)}</span></div>
        <div><span className="label">Worth now</span><span className={`value ${cls(pnl)}`}>{fmtUsd(p.total_value_usd)}</span><span className="sub">{fmtPct(pnl)}</span></div>
        <div><span className="label">Legions</span><span className="value">{p.stakes.length}</span></div>
        <div><span className="label">Agents</span><span className="value">{p.agents.length}</span></div>
      </div>
      {p.stakes.length > 0 && (
        <div className="card block">
          <div className="cardhead"><h2>Stakes</h2></div>
          <div className="tablewrap"><table><thead><tr><th>Legion</th><th className="num">Put in</th><th className="num">Worth</th><th className="num">Share</th><th>Status</th></tr></thead>
            <tbody>{p.stakes.map((s) => <tr key={s.org} className="row" onClick={() => { location.hash = `#/p/${s.org}` }}><td className="text"><b>{s.org_name}</b></td><td className="num">{fmtUsd(s.deposited)}</td><td className={`num ${cls(s.value_usd - s.deposited)}`}>{fmtUsd(s.value_usd)}</td><td className="num">{s.share_pct}%</td><td className="text">{s.status === 'live' ? <span className="pos">● live</span> : <span className="neg">■ halted</span>}</td></tr>)}</tbody></table></div>
        </div>
      )}
      {p.leads.length > 0 && <div className="sub" style={{ padding: '0 4px' }}>Leads {p.leads.map((l) => <a key={l.slug} href={`#/p/${l.slug}`}>{l.name}</a>).reduce((a, b) => [a, ', ', b])}</div>}
      {p.agents.length > 0 && (
        <div className="card block">
          <div className="cardhead"><h2>Agents</h2></div>
          <div className="tablewrap"><table><thead><tr><th>Agent</th><th className="num">Equity</th><th className="num">P&amp;L</th><th className="num">Max DD</th><th>Status</th></tr></thead>
            <tbody>{p.agents.map((a) => <tr key={a.id} className="row" onClick={() => window.dispatchEvent(new CustomEvent('open-agent', { detail: a.id }))}><td className="text"><b>{a.name}</b><br /><span className="sub">{a.strategy || a.runtime}</span></td><td className="num">{fmtUsd(a.equity)}</td><td className={`num ${cls(a.pnl_total_pct)}`}>{fmtPct(a.pnl_total_pct)}</td><td className="num">{a.max_drawdown_pct}%</td><td className="text">{a.status === 'live' ? <span className="pos">● live</span> : <span className="neg">■ halted</span>}</td></tr>)}</tbody></table></div>
        </div>
      )}
    </section>
  )
}

export function Legion({ slug, me, setMe }) {
  const [d, err] = usePoll(`/orgs/${slug}`, 3000)
  const [stats] = usePoll('/stats', 10000)
  const [meP, , reload] = [...usePoll(me ? `/u/${me}` : null, 8000), () => {}]
  const [amt, setAmt] = useState('100')
  const [msg, setMsg] = useState(null)
  if (err) return <section className="social"><div className="err">No legion called {slug}.</div></section>
  if (!d) return <section className="social"><div className="sub" style={{ padding: 16 }}>loading…</div></section>
  const live = d.status === 'live'
  const canDeposit = stats && stats.mode !== 'testnet'
  async function deposit(e) {
    e.preventDefault()
    if (!me) return setMsg('set your handle first')
    const r = await fetch(`/orgs/${slug}/deposit`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ depositor: me, amount_usd: Number(amt) }) })
    const j = await r.json()
    setMsg(r.ok ? `in. ${fmtUsd(j.pool_cash)} unallocated in the pool now.` : (j.detail || 'failed'))
  }
  const link = `${location.origin}/#/p/${slug}`
  return (
    <section className="social">
      <div className="social-head">
        <div><h1>{d.name}</h1><div className="sub">led by <a href={`#/u/${d.leader}`}>{d.leader}</a> · {d.depositors} depositors · {d.members_live}/{d.members} agents live · <span className={live ? 'pos' : 'neg'}>{live ? '● live' : '■ halted'}</span></div></div>
        <span className="spacer" />
        <FollowButton me={me} type="org" id={slug} following={meP?.following} onChange={reload} />
        <button onClick={() => navigator.clipboard?.writeText(link)}>Copy invite link</button>
      </div>
      <blockquote className="mandate big">“{d.mandate}”</blockquote>
      <div className="statrow">
        <div><span className="label">Pooled</span><span className="value">{fmtUsd(d.total_deposited)}</span></div>
        <div><span className="label">Worth now</span><span className={`value ${cls(d.pnl_pct)}`}>{fmtUsd(d.equity)}</span><span className="sub">{fmtPct(d.pnl_pct)}</span></div>
        <div><span className="label">Hard limits</span><span className="value">{d.limits.max_leverage}×</span><span className="sub">stop at {d.limits.drawdown_flatten_pct}% · {d.limits.daily_loss_pct}%/day</span></div>
        <div><span className="label">Markets</span><span className="value" style={{ fontSize: 16 }}>{d.limits.allowed_markets.join(' · ')}</span></div>
        <div><span className="label">Leader's cut</span><span className="value">{d.profit_share_pct}%</span><span className="sub">of profits only</span></div>
      </div>
      <div className="two">
        <div className="card block">
          <div className="cardhead"><h2>Join with your friends</h2></div>
          <div className="pad">
            <p className="sub">Your money sits in the pool under this mandate. Every agent here is capped at {d.limits.max_leverage}× and the whole legion is flattened if it draws down {d.limits.drawdown_flatten_pct}%. You see every fill.</p>
            <WhoAmI me={me} setMe={setMe} />
            <form className="ask" onSubmit={deposit}>
              <input type="number" min="1" step="1" value={amt} onChange={(e) => setAmt(e.target.value)} disabled={!canDeposit || !live} />
              <button className="primary" disabled={!canDeposit || !live}>Deposit {fmtUsd(Number(amt) || 0)}</button>
            </form>
            {!canDeposit && <div className="sub">Deposits in testnet mode go through the Hyperliquid vault flow (coming).</div>}
            {msg && <div className="sub">{msg}</div>}
          </div>
        </div>
        <div className="card block">
          <div className="cardhead"><h2>Who's in</h2></div>
          <div className="pad list">
            {d.depositors_detail.map((x) => <div className="kv" key={x.depositor}><a href={`#/u/${x.depositor}`}>{x.depositor}</a><span>{fmtUsd(x.deposited)} → <span className={cls(x.value_usd - x.deposited)}>{fmtUsd(x.value_usd)}</span> <span className="sub">{x.share_pct}%</span></span></div>)}
          </div>
          <div className="cardhead"><h2>Agents</h2></div>
          <div className="pad list">
            {d.members_detail.map((m) => <div className="kv" key={m.id}><span><a href="#/" onClick={(e) => { e.preventDefault(); window.dispatchEvent(new CustomEvent('open-agent', { detail: m.id })) }}>{m.name}</a> <span className="sub">{m.strategy ? `· ${m.strategy}` : ''}</span></span><span className={cls(m.pnl_total_pct)}>{fmtUsd(m.equity)} ({fmtPct(m.pnl_total_pct)}) {m.status === 'halted' ? '■' : '●'}</span></div>)}
          </div>
        </div>
      </div>
      <div className="card block">
        <div className="cardhead"><h2>Recent decisions</h2><span className="muted">approved, resized and rejected, in the open</span></div>
        <div className="pad list">
          {d.decisions.slice(0, 12).map((o, i) => (
            <div className="kv" key={i}>
              <span><span className="sub" style={{ fontFamily: 'var(--mono)' }}>{new Date(o.ts).toLocaleTimeString([], { hour12: false })}</span> <b>{o.agent}</b> {o.side} {Number(o.requested_size).toFixed(4)} {o.market}</span>
              <span className={o.verdict === 'rejected' ? 'neg' : o.verdict === 'resized' ? 'amber' : 'pos'}>{o.verdict}{o.filled_size ? ` · ${Number(o.filled_size).toFixed(4)}` : ''}{o.verdict !== 'approved' && o.verdict_reason ? ` · ${o.verdict_reason.split(' (')[0]}` : ''}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
