import { apiFetch as fetch, apiUrl } from './api.js'
import React, { useEffect, useRef, useState } from 'react'
import { SkelLines } from './ui.jsx'

// The group chat: the same conversation the iMessage bridge runs, in the browser.
// Say an idea, the Lab tests it, friends back it with a thumbs up, "$50 each" stakes it, the rule fires on the next hack.
// Talks to /huddle/web/{name} and POST /huddle/{id}/messages (backend/app/huddle.py).

const fmtUsd = (v) => (v == null ? '—' : '$' + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }))
const hhmm = (iso) => new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
const BACKING = ['like', 'love', 'emphasize']
const TRY = [
  "let's buy xmr every time a major company gets hacked",
  '$20 each',
  '$50 each',
  'protoss hack: Example Exchange drained for $40M',
  'protoss score',
  'I think the Knicks win game 3 now that Brunson is coming off the injured list',
]

function Thumb({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 10v11H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h3zm0 0 4-8a3 3 0 0 1 3 3v4h5.5a2 2 0 0 1 2 2.3l-1.4 8A2 2 0 0 1 18.1 21H7" />
    </svg>
  )
}

function useHuddle(name) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const load = () =>
    fetch(`/huddle/web/${encodeURIComponent(name)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .then((d) => (setData(d), setErr(null)))
      .catch((e) => setErr(e.message))
  useEffect(() => {
    load()
    const id = setInterval(load, 2500)
    return () => clearInterval(id)
  }, [name])
  return [data, err, load]
}

function Tapbacks({ list }) {
  if (!list?.length) return null
  const on = list.filter((r) => BACKING.includes(r.reaction))
  const off = list.filter((r) => r.reaction === 'dislike')
  return (
    <div className="tapbacks">
      {on.length > 0 && <span title={on.map((r) => r.sender).join(', ')}><Thumb size={12} /> {on.map((r) => r.sender).join(', ')}</span>}
      {off.length > 0 && <span className="muted">pass: {off.map((r) => r.sender).join(', ')}</span>}
    </div>
  )
}

function Bubble({ m, mine, taps, onBack, thesis }) {
  const who = m.from_bot ? 'Protoss' : m.sender
  const live = thesis && thesis.status === 'live'
  return (
    <div className={`hm ${m.from_bot ? 'bot' : mine ? 'mine' : 'them'} k-${m.kind}`}>
      {!mine && <div className="hm-who">{who}</div>}
      <div className="hm-bubble">
        <Tapbacks list={taps} />
        <div className="hm-text">{m.text}</div>
        {m.kind === 'card' && thesis && thesis.status === 'proposed' && (
          <div className="hm-actions">
            <button className="sm" onClick={() => onBack(m.guid, 'like')}><Thumb /> Back it</button>
            <button className="sm ghost" onClick={() => onBack(m.guid, 'dislike')}>Pass</button>
          </div>
        )}
        {m.kind === 'card' && live && <div className="hm-state">live · {fmtUsd(thesis.pledged_usd)} in</div>}
      </div>
      <div className="hm-time">{hhmm(m.ts)}</div>
    </div>
  )
}

function Theses({ list, quorum }) {
  if (!list.length) return <div className="empty"><b>No theses yet</b>Say an idea in the chat. The Lab tests it and posts a card.</div>
  return (
    <div className="th-list">
      {[...list].reverse().filter((t) => t.status !== 'dropped').map((t) => {
        const on = t.backers.filter((b) => b.approved)
        const r = t.record
        return (
          <a key={t.id} className="th" href={apiUrl(`/t/${t.id}`)} target="_blank" rel="noreferrer">
            <div className="th-top"><span className="mono sub">#{t.n}</span><b>{t.label}</b></div>
            <div className="sub">
              {t.kind === 'call' ? (t.outcome || (t.status === 'live' ? 'open call' : `needs backing, ${on.length} of ${quorum}`))
                : t.status === 'proposed' ? `needs backing, ${on.length} of ${quorum}` : t.status}
              {t.kind === 'rule' && ` · ${fmtUsd(t.pledged_usd)} in`}
              {r.closed > 0 && <> · <span className={r.pnl_usd >= 0 ? 'pos' : 'neg'}>{r.up} of {r.closed} up, {r.pnl_usd >= 0 ? '+' : '-'}${Math.abs(r.pnl_usd).toFixed(2)}</span></>}
            </div>
            {on.length > 0 && <div className="chips">{on.map((b) => <span key={b.who}>{b.who}{b.pledge_usd ? ` ${fmtUsd(b.pledge_usd)}` : ''}</span>)}</div>}
            {t.test?.events?.events > 0 && (
              <div className="sub mono">{t.test.market} {t.test.events.event_mean_pct > 0 ? '+' : ''}{t.test.events.event_mean_pct}% after an event vs {t.test.events.any_mean_pct > 0 ? '+' : ''}{t.test.events.any_mean_pct}% any day</div>
            )}
          </a>
        )
      })}
    </div>
  )
}

export default function Huddle({ name = 'demo', me }) {
  const [d, err, reload] = useHuddle(name)
  const [as, setAs] = useState(me || 'Matthew')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const endRef = useRef(null)
  const count = d?.messages.length || 0
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [count])

  const post = async (body) => {
    setBusy(true)
    try {
      await fetch(`/huddle/${d.id}/messages`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ sender: as.trim() || 'Me', ...body }) })
      await reload()
    } finally { setBusy(false) }
  }
  const send = (t) => { const v = (t ?? text).trim(); if (!v || !d) return; setText(''); post({ text: v }) }
  const back = (guid, reaction) => post({ reaction, target_guid: guid })

  if (err && !d) return <section className="one"><div className="err">Could not load this chat ({err}).</div></section>
  if (!d) return <section className="huddle"><div className="card"><SkelLines n={8} /></div></section>

  const taps = {}
  for (const m of d.messages) if (m.kind === 'reaction' && m.target_guid) (taps[m.target_guid] ||= []).push(m)
  const byId = Object.fromEntries(d.theses.map((t) => [t.id, t]))
  const people = Array.from(new Set(['Matthew', 'Lee', 'Sam', ...d.people, as].filter(Boolean)))
  const invite = `${location.origin}/app/#/huddle/${encodeURIComponent(name)}`
  const copy = () => navigator.clipboard?.writeText(invite).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })
  const textGroup = `sms:&body=${encodeURIComponent(`Group chat for ${d.title} on Protoss: say a trade idea, thumbs it up, $50 each. ${invite}`)}`

  return (
    <section className="huddle">
      <div className="huddle-head">
        <div>
          <h1>{d.title}</h1>
          <p className="sub">One idea, tested together. Share a thesis, get {d.quorum} people behind it, and follow the paper results.</p>
        </div>
        <div className="huddle-share">
          <a className="btn sm" href="/app/#/join">Preview funding</a>
          <a className="btn sm" href={textGroup}>Text the group</a>
          <button className="sm ghost" onClick={copy}>{copied ? 'Copied' : 'Copy invite link'}</button>
          {d.org_slug && <a className="btn sm ghost" href={`/app/#/p/${d.org_slug}`}>Legion page</a>}
        </div>
      </div>
      <div className="huddle-grid">
        <div className="card phone">
          <div className="phone-top"><b>{d.title}</b><span className="sub">{people.length} people and Protoss</span></div>
          <div className="hm-list" aria-live="polite">
            {d.messages.filter((m) => m.kind !== 'reaction').map((m) => (
              <Bubble key={m.id} m={m} mine={!m.from_bot && m.sender === as} taps={taps[m.guid]} onBack={back} thesis={m.kind === 'card' ? byId[m.thesis_id] : null} />
            ))}
            <div ref={endRef} />
          </div>
          <div className="as-row">
            <span className="sub">typing as</span>
            <div className="chips pick">{people.map((p) => <button key={p} type="button" className={p === as ? 'on' : ''} onClick={() => setAs(p)}>{p}</button>)}</div>
            <input className="as-new" placeholder="someone else" aria-label="Type as someone else" onKeyDown={(e) => { if (e.key === 'Enter' && e.currentTarget.value.trim()) { setAs(e.currentTarget.value.trim()); e.currentTarget.value = '' } }} />
          </div>
          <form className="hm-compose" onSubmit={(e) => { e.preventDefault(); send() }}>
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="iMessage" disabled={busy} aria-label="Message" />
            <button className="primary" disabled={busy || !text.trim()}>Send</button>
          </form>
        </div>
        <div className="huddle-side">
          <div className="card">
            <div className="cardhead"><h2>Theses</h2><span className="sub">backed by {d.quorum}, staked, scored</span></div>
            <Theses list={d.theses} quorum={d.quorum} />
          </div>
          <div className="card">
            <div className="cardhead"><h2>Try</h2></div>
            <div className="examples tight">{TRY.map((t) => <button key={t} onClick={() => send(t)} disabled={busy}>{t}</button>)}</div>
          </div>
          <p className="sub">Paper money here: pledges go into the legion's ledger and trade inside its limits. With real money each person stakes their own share into the vault; nothing in this chat moves funds.</p>
        </div>
      </div>
    </section>
  )
}
