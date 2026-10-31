import React, { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { stakeInVault } from './hlsign.js'

const PrivyWallet = lazy(() => import('./PrivyWallet.jsx'))

// Join with card: pick a legion, an amount and a payment provider, get a wallet funded, stake it.
// Talks to GET /onboard/options, POST /onboard/session and GET /onboard/session/{id}.

const fmtUsd = (v) => (v == null ? '' : '$' + Number(v).toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) < 100 ? 2 : 0 }))
const RAIL = { card: 'Card', apple_pay: 'Apple Pay', bank: 'Bank transfer' }
const CHAIN = { arbitrum: 'Arbitrum', ethereum: 'Ethereum', base: 'Base', hyperliquid: 'Hyperliquid' }
const PRESETS = [50, 100, 250]
const isAddr = (s) => /^0x[0-9a-fA-F]{40}$/.test((s || '').trim())
const clock = (iso) => { try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) } catch { return '' } }
const short = (a) => (a && a.length > 14 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a || '')

function readWallet() { try { return localStorage.getItem('protoss.wallet') || '' } catch { return '' } }
function saveWallet(w) { try { localStorage.setItem('protoss.wallet', w) } catch { /* private mode */ } }

async function getJson(url) {
  const r = await fetch(url)
  if (!r.ok) throw new Error(String(r.status))
  return r.json()
}

function Skel({ w = '100%', h = 12 }) { return <span className="skel" style={{ width: w, height: h }} aria-hidden="true" /> }

export default function Join({ legion: preset }) {
  const [opts, setOpts] = useState(undefined)      // undefined: loading, null: not available
  const [orgs, setOrgs] = useState(undefined)
  const [legion, setLegion] = useState(preset || '')
  const [amount, setAmount] = useState(100)
  const [custom, setCustom] = useState('')
  const [provider, setProvider] = useState('')
  const [wallet, setWallet] = useState(readWallet)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [session, setSession] = useState(null)
  const [err, setErr] = useState(null)
  const walletRef = useRef(null)

  useEffect(() => {
    let alive = true
    getJson('/onboard/options').then((d) => { if (!alive) return; setOpts(d); setProvider((p) => p || d.providers?.[0]?.id || '') }).catch(() => alive && setOpts(null))
    getJson('/orgs').then((d) => alive && setOrgs(Array.isArray(d) ? d : [])).catch(() => alive && setOrgs([]))
    return () => { alive = false }
  }, [])
  useEffect(() => {
    if (preset || !orgs || orgs.length === 0) return
    setLegion((l) => l || (orgs.find((o) => o.status === 'live') || orgs[0]).slug)
  }, [orgs, preset])

  // while the result panel is open, ask the server every 10s whether the money arrived
  const sid = res?.status === 'ok' ? res.session_id : null
  useEffect(() => {
    if (!sid) return
    let alive = true
    const id = setInterval(() => go(), 10000)
    const go = () => getJson(`/onboard/session/${sid}`).then((d) => {
      if (!alive) return
      setSession(d)
      if (d.status === 'staked' || d.status === 'expired' || d.status === 'failed') clearInterval(id)
    }).catch(() => {})
    go()
    return () => { alive = false; clearInterval(id) }
  }, [sid])

  const providers = opts?.providers || []
  const prov = providers.find((p) => p.id === provider) || null
  const minUsd = prov?.min_usd ?? opts?.min_usd ?? 20
  const org = (orgs || []).find((o) => o.slug === legion) || null
  const amountOk = Number.isFinite(amount) && amount >= minUsd
  const walletOk = isAddr(wallet)
  const canGo = !!opts && !!prov && amountOk && walletOk && !busy
  const chain = CHAIN[opts?.chain] || opts?.chain || ''
  const asset = opts?.asset || ''
  const dest = res?.destination || opts?.destination || null

  const pick = (v) => { setAmount(v); setCustom('') }
  const typeCustom = (v) => { setCustom(v); setAmount(v === '' ? NaN : Number(v)) }

  async function go(e) {
    e.preventDefault()
    if (!canGo) return
    setBusy(true); setErr(null); setRes(null); setSession(null)
    saveWallet(wallet.trim())
    try {
      const body = { legion: legion || null, amount_usd: amount, provider, email: email.trim() || undefined, wallet: wallet.trim(), region: null }
      const r = await fetch('/onboard/session', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : j.detail ? JSON.stringify(j.detail) : `${r.status}`)
      if (j.status === 'needs_wallet') { setErr('Enter the wallet address the funds should go to.'); walletRef.current?.focus(); return }
      setRes(j)
    } catch (ex) {
      setErr(ex.message === 'Failed to fetch' ? 'The API is unreachable.' : ex.message)
    } finally {
      setBusy(false)
    }
  }
  const reset = () => { setRes(null); setSession(null); setErr(null) }

  const loading = opts === undefined
  const off = opts === null

  return (
    <section className="narrow" style={{ maxWidth: 1040 }}>
      <div className="join-head">
        <h1>Join with card</h1>
        <p className="sub">{opts ? `Pay with a card, Apple Pay or a bank transfer. The money lands as ${asset} on ${chain}, in a wallet only you control, then it is staked under the legion's mandate.` : 'Pay with a card or a bank transfer. The money lands in a wallet only you control, then it is staked under the legion\'s mandate.'}</p>
      </div>

      <div className="join">
        <form className="card" onSubmit={go}>
          {res ? <Result res={res} session={session} prov={prov} org={org} onReset={reset} onStaked={() => getJson(`/onboard/session/${res.session_id}`).then(setSession).catch(() => {})} /> : (
            <>
              <div className="fieldset">
                <h3>Legion</h3>
                {orgs === undefined ? <Skel h={36} /> : (
                  <label className="select">
                    <select value={legion} onChange={(e) => setLegion(e.target.value)} aria-label="Legion">
                      {orgs.map((o) => <option key={o.slug} value={o.slug}>{o.name} · led by {o.leader} · {fmtUsd(o.total_deposited)} pooled{o.status === 'live' ? '' : ' · halted'}</option>)}
                      <option value="">No legion yet, just fund my wallet</option>
                    </select>
                  </label>
                )}
                {org && <div className="hint">{org.limits.max_leverage}× cap, stop at {org.limits.drawdown_flatten_pct}% drawdown, {org.limits.allowed_markets.join(', ')}. {org.depositors} people in, {fmtUsd(org.total_deposited)} pooled.</div>}
                {orgs && orgs.length === 0 && <div className="hint">No legions are open yet. You can still fund a wallet and stake later.</div>}
              </div>

              <div className="fieldset">
                <h3>Amount</h3>
                <div className="presets" role="group" aria-label="Amount">
                  {PRESETS.map((v) => <button type="button" key={v} className={amount === v && custom === '' ? 'on' : ''} onClick={() => pick(v)} aria-pressed={amount === v && custom === ''}>${v}</button>)}
                  <div className="field"><span className="prefix">$</span><input type="number" inputMode="decimal" min={minUsd} step="1" placeholder="Other" value={custom} onChange={(e) => typeCustom(e.target.value)} aria-label="Other amount" /></div>
                </div>
                <div className="hint">{Number.isFinite(amount) && !amountOk ? `Minimum ${fmtUsd(minUsd)}.` : `Minimum ${fmtUsd(minUsd)}. Settles in ${asset || 'USDC'}.`}</div>
              </div>

              <div className="fieldset">
                <h3>Pay with</h3>
                {loading && <div className="providers"><Skel h={60} /><Skel h={60} /></div>}
                {off && <div className="notice">Card payments are off in this copy of the dashboard. Start the API to turn them on.</div>}
                {opts && providers.length === 0 && <div className="notice">No payment provider is configured. Set one up in the API and reload.</div>}
                {providers.length > 0 && (
                  <div className="providers" role="radiogroup" aria-label="Payment provider">
                    {providers.map((p) => (
                      <button type="button" key={p.id} role="radio" aria-checked={provider === p.id} className={`provider ${provider === p.id ? 'on' : ''}`} onClick={() => setProvider(p.id)}>
                        <span className="provider-body">
                          <span className="name">{p.name}</span>
                          <span>{(p.rails || []).map((r) => RAIL[r] || r).join(', ')}{p.regions?.length ? ` · ${p.regions.join(', ')}` : ''}{p.min_usd ? ` · from ${fmtUsd(p.min_usd)}` : ''}</span>
                          {p.fee_note && <span className="fee">{p.fee_note}</span>}
                        </span>
                        <span className="radio" aria-hidden="true" />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="fieldset">
                <h3>Your wallet</h3>
                <div className="wallet-row">
                  {opts?.wallet_provider?.app_id && (
                    <div className="soon"><Suspense fallback={<button type="button" disabled>Loading</button>}><PrivyWallet appId={opts.wallet_provider.app_id} onAddress={(a) => { setWallet(a); saveWallet(a) }} /></Suspense></div>
                  )}
                  <input ref={walletRef} value={wallet} onChange={(e) => setWallet(e.target.value)} placeholder="0x…" spellCheck={false} autoComplete="off" aria-label="Your wallet address" aria-invalid={wallet !== '' && !walletOk} />
                  <div className="hint">{wallet !== '' && !walletOk ? 'A wallet address is 0x followed by 40 hex characters.' : 'Funds go to a wallet only you control. Protoss never holds them.'}</div>
                </div>
                <label className="sub" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>Email for the receipt (optional)<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" /></label>
              </div>

              <div className="join-foot">
                <button className="primary" disabled={!canGo}>{busy ? 'Opening…' : amountOk ? `Continue with ${fmtUsd(amount)}` : 'Continue'}</button>
                <span className="muted">{org ? `Staked in ${org.name} once funded.` : 'Stake it in a legion once funded.'}</span>
                {err && <div className="err">{err}</div>}
              </div>
            </>
          )}
        </form>

        <aside className="list" style={{ gap: 16 }}>
          <div className="card pad">
            <h3 style={{ marginBottom: 12 }}>Where the money goes</h3>
            {loading ? <div className="skel-lines"><Skel w="70%" /><Skel w="55%" /><Skel w="90%" /></div> : (
              <div className="facts">
                {chain && <div className="kv"><span>Chain</span><span>{chain}</span></div>}
                {asset && <div className="kv"><span>Asset</span><span>{asset}</span></div>}
                <div className="kv"><span>Destination</span><span>{dest ? (dest.kind === 'vault' ? "the legion's vault" : 'your wallet') : 'your wallet'}</span></div>
                {dest?.address && <div className="kv"><span>Address</span><span className="addr" title={dest.address}>{short(dest.address)}</span></div>}
                <div className="kv"><span>Minimum</span><span>{fmtUsd(minUsd)}</span></div>
              </div>
            )}
          </div>
          {opts?.us_notice && <div className="notice">{opts.us_notice}</div>}
          {opts?.notice && <div className="notice">{opts.notice}</div>}
          {org && (
            <div className="card pad list">
              <div><b style={{ fontWeight: 500 }}>{org.name}</b><div className="sub">led by <a href={`#/u/${org.leader}`}>{org.leader}</a> · {org.members_live}/{org.members} agents live</div></div>
              <div className="mandate">“{org.mandate}”</div>
              <div className="org-stats">
                <span><span className="sub">worth</span>{fmtUsd(org.equity)}</span>
                <span><span className="sub">people</span>{org.depositors}</span>
                <span style={{ gridColumn: '1 / -1' }}><span className="sub">limits</span><span className="limitline">{org.limits.max_leverage}× · stop {org.limits.drawdown_flatten_pct}% · {org.limits.daily_loss_pct}%/day</span></span>
              </div>
              <a className="back" href={`#/p/${org.slug}`}>Open the legion page</a>
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}

function Result({ res, session, prov, org, onReset, onStaked }) {
  if (res.status === 'unavailable') {
    return (
      <div className="fieldset">
        <h3>Not available right now</h3>
        <p className="sub">{res.reason || 'This provider cannot take a payment at the moment.'}</p>
        {res.steps?.length > 0 && <ol className="steps">{res.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>}
        <div className="actions" style={{ margin: 0 }}><button type="button" onClick={onReset}>Back</button></div>
      </div>
    )
  }
  const st = session?.status || 'created'
  const dest = res.destination
  return (
    <>
      <div className="fieldset">
        <h3>Next steps</h3>
        {res.steps?.length > 0 ? <ol className="steps">{res.steps.map((s, i) => <li key={i}>{s}</li>)}</ol> : <p className="sub">Follow the provider's checkout. Funds arrive in your wallet, then they are staked.</p>}
        {dest?.address && <div className="sendto"><span className="sub">Send to</span><span className="addr">{dest.address}</span></div>}
        <div className="actions" style={{ margin: 0 }}>
          {res.url && <a className="btn primary" href={res.url} target="_blank" rel="noopener noreferrer">Open {prov?.name || 'checkout'}</a>}
          <button type="button" className={res.url ? 'ghost' : ''} onClick={onReset}>Start again</button>
          {res.expires_at && <span className="muted">Expires {clock(res.expires_at)}</span>}
        </div>
      </div>
      <div className="fieldset">
        <div className="session" aria-live="polite">
          {(st === 'created' || st === 'redirected') && <><span className="skel" /><span>Waiting for funds</span></>}
          {st === 'funded' && <span className="pos">Funded {fmtUsd(session.funded_usd)}. Staking next.</span>}
          {st === 'funded' && dest?.kind === 'vault' && <Stake res={res} session={session} org={org} onStaked={onStaked} />}
          {st === 'staked' && <span className="pos">Staked {fmtUsd(session.funded_usd)}{org ? ` in ${org.name}` : ''}.</span>}
          {st === 'expired' && <span className="amber">This session expired. Start again.</span>}
          {st === 'failed' && <span className="amber">The payment did not go through, so nothing was staked. Start again or try another card.</span>}
        </div>
      </div>
    </>
  )
}

// Sign `vaultTransfer` from the user's own wallet. The embedded wallet (window.protossWallet, set once Privy is wired)
// signs Hyperliquid's chain-1337 typed data; an injected wallet may refuse it, and we say so rather than guess.
function Stake({ res, session, org, onStaked }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  async function stake() {
    setErr(null); setBusy(true)
    try {
      const provider = window.protossWallet || window.ethereum
      if (!provider) throw new Error('No wallet in this browser. Open the wallet that received the funds and try again.')
      const [account] = await provider.request({ method: 'eth_requestAccounts' })
      if (!account || account.toLowerCase() !== (res.wallet || '').toLowerCase()) throw new Error(`Switch to ${short(res.wallet)}, the wallet the funds went to.`)
      const b = await getJson('/builder').catch(() => ({}))
      const usd = Math.floor((session.funded_usd || 0) * 100) / 100
      if (!(usd >= 1)) throw new Error('Nothing to stake yet. Wait for the funds to show, then try again.')
      const j = await stakeInVault(provider, { account, vault: res.destination.address, usd, mainnet: b.network !== 'Testnet' })
      await fetch(`/onboard/session/${res.session_id}/staked`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ tx: JSON.stringify(j.response || '').slice(0, 200) }) })
      onStaked?.()
    } catch (e) {
      const m = e?.message || String(e)
      setErr(/chain ?id|chainId/i.test(m) ? 'This wallet will not sign Hyperliquid actions. Sign in with email above for one that does, or stake from app.hyperliquid.xyz.' : m)
    } finally {
      setBusy(false)
    }
  }
  return (
    <span className="actions" style={{ margin: 0 }}>
      <button type="button" className="primary" disabled={busy} onClick={stake}>{busy ? 'Signing' : `Stake ${fmtUsd(session.funded_usd)}${org ? ` in ${org.name}` : ''}`}</button>
      {err && <span className="amber">{err}</span>}
    </span>
  )
}
