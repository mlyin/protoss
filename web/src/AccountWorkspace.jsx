import WalletChooser from './WalletChooser.jsx'
import React, { useEffect, useRef, useState } from 'react'
import './AccountWorkspace.css'

const ADDRESS = /^0x[0-9a-fA-F]{40}$/
const short = address => `${address.slice(0, 6)}…${address.slice(-4)}`
const number = value => value == null || value === '' || !Number.isFinite(Number(value)) ? null : Number(value)
const money = value => number(value) == null ? 'Unavailable' : new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(Number(value))

export async function readPositions(address, signal) {
  const info = async body => {
    const response = await fetch('https://api.hyperliquid.xyz/info', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'omit',
      body: JSON.stringify(body), signal,
    })
    if (!response.ok) throw new Error('Hyperliquid is unavailable. Try again.')
    return response.json()
  }
  const dexs = await info({ type: 'perpDexs' })
  if (!Array.isArray(dexs)) throw new Error('Could not verify the market list.')
  const names = [...new Set(['', ...dexs.filter(d => d && typeof d.name === 'string').map(d => d.name)])]
  const positions = [], unavailable = []
  // Bound concurrency. Read every listed venue, including builder markets such as xyz.
  for (let start = 0; start < names.length; start += 4) {
    if (signal.aborted) throw new Error('Request cancelled')
    await Promise.all(names.slice(start, start + 4).map(async dex => {
      try {
        const state = await info({ type: 'clearinghouseState', user: address, dex })
        if (!Array.isArray(state.assetPositions)) throw new Error('Invalid positions response')
        for (const item of state.assetPositions) {
          const p = item.position
          if (!p || typeof p.coin !== 'string' || number(p.szi) == null) throw new Error('Invalid position')
          if (Number(p.szi) !== 0) positions.push({ ...p, dex })
        }
      } catch { unavailable.push(dex || 'Core') }
    }))
  }
  if (signal.aborted) throw new Error('Request cancelled')
  // the connected owner's own fills, newest first (spot pairs show as their index, e.g. @142)
  let fills = null
  try {
    const rows = await info({ type: 'userFills', user: address })
    fills = Array.isArray(rows) ? rows.slice(0, 10) : null
  } catch { fills = null }
  return { positions: positions.sort((a, b) => a.coin.localeCompare(b.coin)), unavailable, fills, checked: new Date(), venues: names.length }
}

function usePositions(address) {
  const [state, setState] = useState({ address: '', data: null, loading: false, error: '' })
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    setState({ address, data: null, loading: !!address, error: '' })
    if (!address) return
    let alive = true, timer, controller
    const load = async () => {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 20000)
      setState(previous => ({ ...previous, loading: true }))
      try {
        const data = await readPositions(address, controller.signal)
        if (alive) setState({ address, data, loading: false, error: '' })
      } catch (error) {
        if (alive) setState(previous => ({ ...previous, loading: false, error: controller.signal.aborted ? 'The account request timed out. Try again.' : error.message }))
      } finally {
        clearTimeout(timeout)
        if (alive) timer = setTimeout(load, 30000)
      }
    }
    load()
    return () => { alive = false; clearTimeout(timer); controller?.abort() }
  }, [address, revision])
  return [state.address === address ? state : { data: null, loading: !!address, error: '' }, () => setRevision(n => n + 1)]
}

function Friends({ address }) {
  const storageKey = `protoss.friends.${address.toLowerCase()}`
  const [friends, setFriends] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || '[]')
      return Array.isArray(saved) ? saved.filter(f => typeof f.name === 'string' && /^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(f.username)) : []
    } catch { return [] }
  })
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [username, setUsername] = useState('')
  const [error, setError] = useState('')
  const save = next => {
    try { localStorage.setItem(storageKey, JSON.stringify(next)); setFriends(next); setError(''); return true }
    catch { setError('This browser could not save your friends.'); return false }
  }
  const add = e => {
    e.preventDefault()
    const handle = username.trim().replace(/^@/, '')
    if (!/^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(handle)) { setError('Enter a Telegram username with 5 to 32 letters, numbers, or underscores.'); return }
    if (friends.some(f => f.username.toLowerCase() === handle.toLowerCase())) { setError('This friend is already in your list.'); return }
    if (save([...friends, { name: name.trim() || handle, username: handle }])) { setName(''); setUsername(''); setEditing(false) }
  }
  return <section className="account-friends" aria-labelledby="friends-title">
    <div className="account-section-heading"><h2 id="friends-title">Friends</h2><button className="account-text-button" onClick={() => setEditing(!editing)}>{editing ? 'Cancel' : 'Add friend'}</button></div>
    <p className="account-note">Telegram contacts you save here. Stored on this browser for this wallet.</p>
    {!friends.length && <div className="account-empty"><p>No friends added yet.</p><span>Add a Telegram username to open their chat. Their positions remain private.</span></div>}
    <div className="account-friend-list">{friends.map(f => <div className="account-friend" key={f.username}>
      <span className="friend-avatar" aria-hidden="true">{f.name[0].toUpperCase()}</span><a href={`https://t.me/${encodeURIComponent(f.username)}`} target="_blank" rel="noreferrer"><b>{f.name}</b><small>@{f.username}</small></a><button className="account-text-button" aria-label={`Remove ${f.name}`} onClick={() => save(friends.filter(x => x.username !== f.username))}>Remove</button>
    </div>)}</div>
    {editing && <form className="friend-form" onSubmit={add}><label>Name<input value={name} maxLength={60} onChange={e => setName(e.target.value)} autoComplete="off" /></label><label>Telegram username<input required value={username} maxLength={33} onChange={e => setUsername(e.target.value)} autoComplete="off" /></label><button className="btn primary">Save friend</button></form>}
    {error && <p className="err" role="alert">{error}</p>}
  </section>
}

export default function AccountWorkspace({ embedded = false }) {
  const [address, setAddress] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [choosingWallet, setChoosingWallet] = useState(false)
  const connectLock = useRef(false)
  const [connectError, setConnectError] = useState('')
  const providerRef = useRef(null)
  const cleanupRef = useRef(null)
  const connectionAttempt = useRef(0)
  const [state, refresh] = usePositions(address)
  useEffect(() => () => { connectionAttempt.current++; cleanupRef.current?.() }, [])
  const disconnect = () => {
    connectionAttempt.current++
    cleanupRef.current?.(); cleanupRef.current = null; providerRef.current = null
    setAddress(''); setConnectError(''); setConnecting(false); setChoosingWallet(false); connectLock.current = false
  }
  const connect = async provider => {
    if (connectLock.current) return
    connectLock.current = true
    cleanupRef.current?.(); cleanupRef.current = null; providerRef.current = null
    setAddress('')
    const attempt = ++connectionAttempt.current
    setConnecting(true); setConnectError('')
    try {
      // Access to the selected public address only. No signature, chain switch, or transaction.
      const accounts = await provider.request({ method: 'eth_requestAccounts' })
      if (attempt !== connectionAttempt.current) return
      if (!ADDRESS.test(accounts?.[0])) throw new Error('No wallet account was selected.')
      cleanupRef.current?.()
      providerRef.current = provider
      const active = () => providerRef.current === provider && attempt === connectionAttempt.current
      const lost = () => {
        if (!active()) return
        disconnect(); setConnectError('Wallet disconnected. Connect again to view your positions.')
      }
      const changed = accounts => {
        if (!active()) return
        if (ADDRESS.test(accounts?.[0])) setAddress(accounts[0])
        else lost()
      }
      provider.on?.('accountsChanged', changed)
      provider.on?.('disconnect', lost)
      cleanupRef.current = () => { provider.removeListener?.('accountsChanged', changed); provider.removeListener?.('disconnect', lost) }
      setAddress(accounts[0]); setChoosingWallet(false)
    } catch (error) {
      if (attempt === connectionAttempt.current) setConnectError(error.code === 4001 ? 'Connection cancelled. Your wallet was not connected.' : 'Could not connect your wallet. Check the wallet and try again.')
    } finally { if (attempt === connectionAttempt.current) { setConnecting(false); connectLock.current = false } }
  }
  return <section className={`account-workspace ${embedded ? 'embedded' : ''}`} aria-label="Friends and positions">
    <header className="account-header"><img src="/probe/idle.svg" alt="" /><div><h2>Your circle</h2><p>{address ? short(address) : 'Your friends. Your positions.'}</p></div>{address && <button className="account-text-button" onClick={disconnect}>Disconnect</button>}</header>
    {!address ? <div className="account-connect">
      <div className="account-connect-mark"><img src="/probe/idle.svg" alt="Probe" /></div>
      <h2>Connect your Hyperliquid account</h2><p>See your actual Hyperliquid positions and keep your friends close.</p>
      {choosingWallet ? <WalletChooser onSelect={connect} onCancel={disconnect} busy={connecting} />
        : <button className="btn primary" onClick={() => { setConnectError(''); setChoosingWallet(true) }}>Connect Hyperliquid</button>}
      <span>Read-only. No trades or signatures.</span>
      {connectError && <p className="account-error" role="alert">{connectError}</p>}
    </div> : <div className="account-content" key={address.toLowerCase()}>
      <Friends address={address} />
      <section className="account-positions" aria-labelledby="positions-title">
        <div className="account-section-heading"><h2 id="positions-title">My positions</h2><button className="account-text-button" onClick={refresh} disabled={state.loading}>{state.loading ? 'Refreshing…' : 'Refresh'}</button></div>
        <p className="account-note">Hyperliquid mainnet · Your connected wallet only</p>
        {state.error && <p className="account-error" role="alert">{state.error}{state.data && ' Showing the last successful response.'}</p>}
        {state.loading && !state.data && <p className="account-note" role="status">Reading positions from Hyperliquid…</p>}
        {state.data && <>
          {state.data.unavailable.length > 0 && <p className="account-error" role="alert">Could not load {state.data.unavailable.join(', ')}. Positions below may be incomplete.</p>}
          {!state.data.positions.length && <div className="account-empty"><p>{state.data.unavailable.length ? 'No positions returned from the available markets.' : 'No open positions.'}</p><span>{state.data.unavailable.length ? 'Refresh to check the missing markets.' : `Checked all ${state.data.venues} perpetual venues. No sample positions are shown.`}</span></div>}
          <div className="position-list">{state.data.positions.map(p => <article className="real-position" key={`${p.dex}:${p.coin}`}>
            <div className="position-heading"><b>{p.coin}</b><span className={Number(p.szi) > 0 ? 'long' : 'short'}>{Number(p.szi) > 0 ? 'Long' : 'Short'}</span></div>
            <dl><div><dt>Size</dt><dd>{Math.abs(Number(p.szi)).toLocaleString(undefined, { maximumFractionDigits: 10 })}</dd></div><div><dt>Entry price</dt><dd>{money(p.entryPx)}</dd></div><div><dt>Position value</dt><dd>{money(p.positionValue)}</dd></div><div><dt>Unrealized P&amp;L</dt><dd>{money(p.unrealizedPnl)}</dd></div></dl>
          </article>)}</div>
          <div className="owner-fills"><h3>My recent fills</h3>
            {state.data.fills === null ? <p className="account-error" role="alert">Could not load your fills. Positions above are still current.</p>
              : !state.data.fills.length ? <p className="account-note">No fills yet.</p>
              : <table><tbody>{state.data.fills.map(f => <tr key={`${f.tid}-${f.time}`}>
                <td>{new Date(f.time).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
                <td>{f.coin}</td><td className={f.side === 'B' ? 'long' : 'short'}>{f.side === 'B' ? 'Buy' : 'Sell'} {f.sz}</td><td>{money(f.px)}</td>
                <td>{number(f.closedPnl) ? money(f.closedPnl) : ''}</td></tr>)}</tbody></table>}
          </div>
          <p className="account-updated">Checked {state.data.checked.toLocaleTimeString()} · Updates every 30 seconds</p>
        </>}
      </section>
    </div>}
  </section>
}
