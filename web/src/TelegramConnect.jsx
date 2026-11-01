import WalletChooser from './WalletChooser.jsx'
import React, { useEffect, useRef, useState } from 'react'
import { privateApiFetch } from './api.js'
import './PrivateAccount.css'

export default function TelegramConnect({ token }) {
  const [connection, setConnection] = useState(null)
  const [busy, setBusy] = useState(false)
  const [choosingWallet, setChoosingWallet] = useState(false)
  const attempt = useRef(0)
  const [error, setError] = useState('')
  const alive = useRef(true)
  const lock = useRef(false)

  useEffect(() => {
    alive.current = true
    const controller = new AbortController()
    if (!token) setError('Open your private connection link from the Telegram bot.')
    else privateApiFetch('/telegram/connect', {
      headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
    }).then(async response => {
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not open this connection link.')
      if (alive.current) setConnection(data)
    }).catch(error => { if (alive.current) setError(error.message) })
    return () => { alive.current = false; attempt.current++; controller.abort() }
  }, [token])

  async function connect(provider) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    const currentAttempt = ++attempt.current
    try {
      const accounts = await provider.request({ method: 'eth_requestAccounts' })
      if (!alive.current || currentAttempt !== attempt.current) return
      const wallet = accounts?.[0]
      if (!/^0x[0-9a-fA-F]{40}$/.test(wallet || '')) throw new Error('No wallet account was selected.')
      const message = '0x' + Array.from(new TextEncoder().encode(connection.challenge), b => b.toString(16).padStart(2, '0')).join('')
      const signature = await provider.request({ method: 'personal_sign', params: [message, wallet] })
      if (!alive.current || currentAttempt !== attempt.current) return
      const selected = await provider.request({ method: 'eth_accounts' })
      if (!alive.current || currentAttempt !== attempt.current) return
      if (selected?.[0]?.toLowerCase() !== wallet.toLowerCase()) throw new Error('Wallet selection changed. Connect again with the wallet you want to use.')
      const response = await privateApiFetch('/telegram/connect', {
        method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ wallet, signature }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not verify wallet ownership.')
      if (alive.current && currentAttempt === attempt.current) { setConnection(current => ({ ...current, ...data })); setChoosingWallet(false) }
    } catch (error) {
      if (alive.current && currentAttempt === attempt.current) setError(error.code === 4001 ? 'Connection cancelled. No ownership signature was saved.' : error.message)
    } finally {
      if (currentAttempt === attempt.current) { lock.current = false; if (alive.current) setBusy(false) }
    }
  }

  return <section className="private-account" aria-labelledby="connection-title">
    <div className="private-heading"><img src="/probe/idle.svg" alt="" /><div><p>Private Telegram connection</p><h1 id="connection-title">Your chat. Your wallet.</h1></div></div>
    <p className="sub">Link your Telegram identity to your own wallet. This signature proves ownership. It cannot place a trade or move funds.</p>
    {!connection && !error && <p role="status">Loading your private link…</p>}
    {connection && <div className="card pad list">
      <div className="kv"><span>Telegram account</span><strong>{connection.display_name}</strong></div>
      <div className="kv"><span>Group</span><strong>{connection.group}</strong></div>
      {connection.wallet ? <div className="notice" role="status"><h2>Wallet ownership verified</h2>
        <p className="addr">{connection.wallet}</p><p>Return to Telegram to continue your conversation. Your positions stay in your own account view.</p>
        <a className="btn primary" href="/app/">View my positions</a>
      </div> : <>
        <details><summary>Read the ownership message</summary><pre>{connection.challenge}</pre></details>
        {choosingWallet ? <WalletChooser onSelect={connect} busy={busy} onCancel={() => { attempt.current++; lock.current = false; setBusy(false); setChoosingWallet(false); setError('') }} />
          : <button className="primary" onClick={() => setChoosingWallet(true)}>Connect Hyperliquid wallet</button>}
      </>}
      <p className="sub">Keep this link private. If it expires, request a new connection link in Telegram.</p>
    </div>}
    {error && <p className="err" role="alert">{error}</p>}
    <a className="private-return" href="https://t.me/ProtossTradingDemoBot" target="_blank" rel="noreferrer">Return to Telegram ↗</a>
  </section>
}
