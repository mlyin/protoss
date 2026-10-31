import React, { useEffect, useState } from 'react'
import { SkelLines, St } from './ui.jsx'

// Social layer: the public feed, a person's page, and a legion's join page.

const fmtUsd = (v) => (v == null ? '—' : '$' + Number(v).toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) < 100 ? 2 : 0 }))
const fmtPct = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%')
const cls = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '')
const when = (iso) => { const d = new Date(iso); const s = (Date.now() - d) / 1000; return s < 60 ? 'now' : s < 3600 ? `${Math.floor(s / 60)}m` : s < 86400 ? `${Math.floor(s / 3600)}h` : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) }

export function useMe() {
  const [me, setMe] = useState(() => { try { return localStorage.getItem('protoss.me') || '' } catch { return '' } })
  const set = (h) => { setMe(h); try { localStorage.setItem('protoss.me', h) } catch { /* private mode */ } }
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
  return <button className={`follow sm ${on ? 'on' : ''}`} disabled={busy} onClick={(e) => { e.stopPropagation(); go() }}>{on ? 'Following' : 'Follow'}</button>
}

export function WhoAmI({ me, setMe }) {
  const [v, setV] = useState(me)
  return (
    <form className="whoami" onSubmit={(e) => { e.preventDefault(); setMe(v.trim().toLowerCase()) }}>
      <span className="sub">you are</span>
      <input value={v} onChange={(e) => setV(e.target.value)} placeholder="handle" aria-label="Your handle" />
      <button>{me ? 'Switch' : 'Set'}</button>
    </form>
  )
}

export function Feed({ me, setMe }) {
  const [mine, setMine] = useState(false)
  const [items, err] = usePoll(`/feed?limit=80${mine && me ? `&handle=${encodeURIComponent(me)}` : ''}`, 3000)
  const [prof] = usePoll(me ? `/u/${me}` : null, 8000)
  const following = prof?.following || []
  return (
    <section className="social narrow">
      <div className="social-head">
        <h1>Feed</h1>
        <div className="seg" role="group" aria-label="Who"><button className={!mine ? 'on' : ''} onClick={() => setMine(false)} aria-pressed={!mine}>Everyone</button><button className={mine ? 'on' : ''} onClick={() => setMine(true)} disabled={!me} aria-pressed={mine}>Following</button></div>
        <span className="spacer" />
        <WhoAmI me={me} setMe={setMe} />
      </div>
      {err && <div className="notice warn">Feed unreachable ({err}).</div>}
      <div className="stream">
        {!items && !err && <div className="pad"><SkelLines n={5} widths={['70%', '85%', '60%', '90%', '75%']} /></div>}
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
        {items && items.length === 0 && <div className="empty"><b>{mine ? 'Nothing from the people and legions you follow yet' : 'Quiet arena'}</b><span>{mine ? 'Follow an agent or a legion and its fills show up here.' : 'Fills, rejections, halts and deposits show up here as they happen.'}</span></div>}
      </div>
    </section>
  )
}

export function Profile({ handle, me }) {
  const [p, err] = usePoll(`/u/${handle}`, 5000)
  const [meP] = usePoll(me ? `/u/${me}` : null, 8000)
  if (err) return <section className="social narrow"><div className="card empty"><b>No one called {handle} here yet</b><span>Handles are set on the feed page. Check the spelling, or go back to the arena.</span><a className="btn" href="#/">Back to the arena</a></div></section>
  if (!p) return <section className="social narrow"><div className="social-head"><span className="skel" style={{ width: 44, height: 44, borderRadius: 22 }} /><div style={{ flex: 1 }}><SkelLines n={2} widths={['40%', '60%']} /></div></div><div className="card"><SkelLines n={1} widths={['100%']} /></div></section>
  const pnl = p.total_deposited ? ((p.total_value_usd - p.total_deposited) / p.total_deposited) * 100 : null
  return (
    <section className="social narrow">
      <div className="social-head">
        <div className="avatar">{handle.slice(0, 1).toUpperCase()}</div>
        <div><h1>{p.display_name}</h1><div className="sub">@{handle}{p.bio ? ` · ${p.bio}` : ''} · {p.followers} followers</div></div>
        <span className="spacer" />
        {me && me !== handle && <FollowButton me={me} type="user" id={handle} following={meP?.following} />}
      </div>
      <div className="card statrow">
        <div><span className="label">Staked</span><span className="value">{fmtUsd(p.total_deposited)}</span></div>
        <div><span className="label">Worth now</span><span className={`value ${cls(pnl)}`}>{fmtUsd(p.total_value_usd)}</span><span className="sub">{fmtPct(pnl)}</span></div>
        <div><span className="label">Legions</span><span className="value">{p.stakes.length}</span></div>
        <div><span className="label">Agents</span><span className="value">{p.agents.length}</span></div>
      </div>
      {p.stakes.length > 0 && (
        <div className="card">
          <div className="cardhead"><h2>Stakes</h2></div>
          <div className="tablewrap"><table className="mini"><thead><tr><th>Legion</th><th className="num">Put in</th><th className="num">Worth</th><th className="num">Share</th><th>Status</th></tr></thead>
            <tbody>{p.stakes.map((s) => <tr key={s.org} className="row" onClick={() => { location.hash = `#/p/${s.org}` }}><td className="text"><b>{s.org_name}</b></td><td className="num">{fmtUsd(s.deposited)}</td><td className={`num ${cls(s.value_usd - s.deposited)}`}>{fmtUsd(s.value_usd)}</td><td className="num">{s.share_pct}%</td><td className="text"><St live={s.status === 'live'} /></td></tr>)}</tbody></table></div>
        </div>
      )}
      {p.leads.length > 0 && <div className="sub">Leads {p.leads.map((l) => <a key={l.slug} href={`#/p/${l.slug}`}>{l.name}</a>).reduce((a, b) => [a, ', ', b])}</div>}
      {p.agents.length > 0 && (
        <div className="card">
          <div className="cardhead"><h2>Agents</h2></div>
          <div className="tablewrap"><table className="mini"><thead><tr><th>Agent</th><th className="num">Equity</th><th className="num">P&amp;L</th><th className="num">Max DD</th><th>Status</th></tr></thead>
            <tbody>{p.agents.map((a) => <tr key={a.id} className="row" onClick={() => window.dispatchEvent(new CustomEvent('open-agent', { detail: a.id }))}><td className="text"><b>{a.name}</b><span className="sub">{a.strategy || a.runtime}</span></td><td className="num">{fmtUsd(a.equity)}</td><td className={`num ${cls(a.pnl_total_pct)}`}>{fmtPct(a.pnl_total_pct)}</td><td className="num">{a.max_drawdown_pct}%</td><td className="text"><St live={a.status === 'live'} /></td></tr>)}</tbody></table></div>
        </div>
      )}
      {p.stakes.length === 0 && p.agents.length === 0 && <div className="card empty"><b>Nothing staked yet</b><span>Join a legion with $100 and it shows up here.</span><a className="btn" href="#/join">Join with card</a></div>}
    </section>
  )
}

export function Legion({ slug, me, setMe }) {
  const [d, err] = usePoll(`/orgs/${slug}`, 3000)
  const [stats] = usePoll('/stats', 10000)
  const [meP, , reload] = [...usePoll(me ? `/u/${me}` : null, 8000), () => {}]
  const [amt, setAmt] = useState('100')
  const [msg, setMsg] = useState(null)
  const [copied, setCopied] = useState(false)
  if (err) return <section className="social"><div className="card empty"><b>No legion called {slug}</b><span>It may have been renamed, or the link is wrong.</span><a className="btn" href="#/">Back to the arena</a></div></section>
  if (!d) return <section className="social"><div><span className="skel lg" style={{ width: 280, height: 32 }} /><div style={{ marginTop: 10 }}><span className="skel" style={{ width: 360 }} /></div></div><div className="card statrow"><div><SkelLines n={2} widths={['50%', '80%']} /></div><div><SkelLines n={2} widths={['50%', '80%']} /></div><div><SkelLines n={2} widths={['50%', '80%']} /></div></div></section>
  const live = d.status === 'live'
  const canDeposit = stats && stats.mode !== 'testnet'
  async function deposit(e) {
    e.preventDefault()
    if (!me) return setMsg('Set your handle first.')
    const r = await fetch(`/orgs/${slug}/deposit`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ depositor: me, amount_usd: Number(amt) }) })
    const j = await r.json()
    setMsg(r.ok ? `In. ${fmtUsd(j.pool_cash)} unallocated in the pool now.` : (j.detail || 'The deposit did not go through.'))
  }
  // /l/<slug> serves link-preview tags (iMessage, WhatsApp, X) and forwards to this page
  const link = `${location.origin}/l/${slug}${me ? `?from=${encodeURIComponent(me)}` : ''}`
  const sms = `sms:&body=${encodeURIComponent(`${d.name}: ${fmtUsd(d.equity)} pooled, stop at ${d.limits.drawdown_flatten_pct}%. Want in? ${link}`)}`
  const copy = () => { navigator.clipboard?.writeText(link).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) }) }
  return (
    <section className="social">
      <div className="social-head">
        <div><h1>{d.name}</h1><div className="sub">led by <a href={`#/u/${d.leader}`}>{d.leader}</a> · {d.depositors} depositors · {d.members_live}/{d.members} agents live · <St live={live} /></div></div>
        <span className="spacer" />
        <FollowButton me={me} type="org" id={slug} following={meP?.following} onChange={reload} />
        <a className="btn" href={`#/huddle/${encodeURIComponent(slug)}`}>Group chat</a>
        <a className="btn" href={sms}>Text an invite</a>
        <button onClick={copy}>{copied ? 'Copied' : 'Copy invite link'}</button>
      </div>
      <blockquote className="mandate big">“{d.mandate}”</blockquote>
      <div className="card statrow">
        <div><span className="label">Pooled</span><span className="value">{fmtUsd(d.total_deposited)}</span></div>
        <div><span className="label">Worth now</span><span className={`value ${cls(d.pnl_pct)}`}>{fmtUsd(d.equity)}</span><span className="sub">{fmtPct(d.pnl_pct)}</span></div>
        <div><span className="label">Hard limits</span><span className="value limit">{d.limits.max_leverage}×</span><span className="sub">stop at {d.limits.drawdown_flatten_pct}% · {d.limits.daily_loss_pct}%/day</span></div>
        <div><span className="label">Markets</span><span className="value" style={{ fontSize: 15, lineHeight: '20px', paddingTop: 4 }}>{d.limits.allowed_markets.join(' · ')}</span></div>
        <div><span className="label">Leader's cut</span><span className="value">{d.profit_share_pct}%</span><span className="sub">of profits only</span></div>
      </div>
      <div className="two">
        <div className="card">
          <div className="cardhead"><h2>Join with your friends</h2></div>
          <div className="pad list" style={{ gap: 16 }}>
            <p className="sub">Your money sits in the pool under this mandate. Every agent here is capped at {d.limits.max_leverage}× and the whole legion is flattened if it draws down {d.limits.drawdown_flatten_pct}%. You see every fill.</p>
            <WhoAmI me={me} setMe={setMe} />
            <form className="ask plain" onSubmit={deposit}>
              <input type="number" min="1" step="1" value={amt} onChange={(e) => setAmt(e.target.value)} disabled={!canDeposit || !live} aria-label="Amount in dollars" />
              <button className="primary" disabled={!canDeposit || !live}>Deposit {fmtUsd(Number(amt) || 0)}</button>
            </form>
            {!canDeposit && <div className="sub">Deposits in testnet mode go through the Hyperliquid vault flow (coming).</div>}
            {msg && <div className="sub">{msg}</div>}
            <div className="inline-links"><span className="muted">No USDC yet?</span><a className="btn sm" href={`#/join?legion=${encodeURIComponent(slug)}`}>Join with card</a></div>
          </div>
        </div>
        <div className="card">
          <div className="cardhead"><h2>Who's in</h2></div>
          <div className="pad list">
            {d.depositors_detail.map((x) => <div className="kv" key={x.depositor}><a href={`#/u/${x.depositor}`}>{x.depositor}</a><span>{fmtUsd(x.deposited)} → <span className={cls(x.value_usd - x.deposited)}>{fmtUsd(x.value_usd)}</span> <span className="sub">{x.share_pct}%</span></span></div>)}
          </div>
          <div className="cardhead"><h2>Agents</h2></div>
          <div className="pad list">
            {d.members_detail.length === 0 && <div className="muted">No agents allocated yet</div>}
            {d.members_detail.map((m) => <div className="kv" key={m.id}><span><a href="#/" onClick={(e) => { e.preventDefault(); window.dispatchEvent(new CustomEvent('open-agent', { detail: m.id })) }}>{m.name}</a>{m.strategy ? <span className="muted"> · {m.strategy}</span> : null}</span><span className={cls(m.pnl_total_pct)}>{fmtUsd(m.equity)} ({fmtPct(m.pnl_total_pct)})</span></div>)}
          </div>
        </div>
      </div>
      <div className="card">
        <div className="cardhead"><h2>Recent decisions</h2><span className="muted">approved, resized and rejected, in the open</span></div>
        {d.decisions.length === 0 ? <div className="empty"><b>No decisions yet</b><span>Every order an agent asks for shows up here with its verdict.</span></div> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>Time</th><th>Agent</th><th>Side</th><th className="num">Size</th><th>Market</th><th>Verdict</th><th>Reason</th></tr></thead>
              <tbody>
                {d.decisions.slice(0, 12).map((o, i) => (
                  <tr key={i}>
                    <td className="sub">{new Date(o.ts).toLocaleTimeString([], { hour12: false })}</td>
                    <td className="text"><b>{o.agent}</b></td>
                    <td className={o.side === 'buy' ? 'pos' : 'neg'}>{o.side}</td>
                    <td className="num">{Number(o.requested_size).toFixed(4)}</td>
                    <td>{o.market}</td>
                    <td className={o.verdict === 'rejected' ? 'neg' : o.verdict === 'resized' ? 'amber' : 'pos'}>{o.verdict}{o.filled_size ? ` · ${Number(o.filled_size).toFixed(4)}` : ''}</td>
                    <td className="text sub">{o.verdict !== 'approved' && o.verdict_reason ? o.verdict_reason.split(' (')[0] : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
