import React, { useEffect, useState } from 'react'

export default function TelegramConnect({ token }) {
  const [connection, setConnection] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let alive = true
    setConnection(null); setError('')
    if (!token) { setError('Open your private connection link from the Telegram bot.'); return }
    fetch('/telegram/connect', { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' })
      .then(async (r) => { const data = await r.json(); if (!r.ok) throw new Error(data.detail || 'Could not load this link.'); return data })
      .then((data) => { if (alive) setConnection(data) })
      .catch((e) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [token])
  async function connect() {
    setBusy(true); setError('')
    try {
      const provider = window.protossWallet || window.ethereum
      if (!provider) throw new Error('Open this private link in your wallet browser, or on a desktop with your wallet extension. Telegram’s browser may not expose your wallet.')
      const [wallet] = await provider.request({ method: 'eth_requestAccounts' })
      if (!wallet) throw new Error('No wallet account selected.')
      const bytes = new TextEncoder().encode(connection.challenge)
      const message = '0x' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
      const signature = await provider.request({ method: 'personal_sign', params: [message, wallet] })
      const response = await fetch('/telegram/connect', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ wallet, signature }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Wallet verification failed.')
      setConnection((current) => ({ ...current, wallet: data.wallet }))
    } catch (e) {
      setError(e.code === 4001 ? 'Signature declined. No funds moved.' : e.message)
    } finally { setBusy(false) }
  }
  return <section className="narrow" style={{ maxWidth: 650 }}>
    <h1>Your Telegram wallet</h1>
    <p className="sub" style={{ margin: '16px 0 28px' }}>Connect your own wallet to your Telegram identity. This step proves ownership. It does not authorize a deposit or a trade.</p>
    <div className="card pad list" style={{ gap: 20 }}>
      {connection && <>
        <div className="kv"><span>Participant</span><strong>{connection.display_name}</strong></div>
        <div className="kv"><span>Telegram ID</span><span className="mono">{connection.telegram_user_id}</span></div>
        <div className="kv"><span>Group</span><span>{connection.group}</span></div>
        <div className="kv"><span>Mode</span><span>{connection.mode}</span></div>
        {connection.wallet ? <>
          <h2>Wallet ownership verified</h2><p className="addr" style={{ overflowWrap: 'anywhere' }}>{connection.wallet}</p>
          <p className="sub">Return to Telegram and send /status. Your deposit has not been checked.</p>
          {connection.vault_url ? <a className="btn primary" href={connection.vault_url} target="_blank" rel="noopener noreferrer">Review the vault on Hyperliquid</a> : <p className="notice">This demo has no live vault deposit link. Chat pledges use paper money in sim and paper modes.</p>}
        </> : <>
          <details><summary>Read the ownership message</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 12 }}>{connection.challenge}</pre></details>
          <button className="primary" onClick={connect} disabled={busy}>{busy ? 'Waiting for your wallet…' : 'Connect wallet and sign ownership message'}</button>
          <p className="sub">Keep this link private. Each of the two Telegram accounts connects a different wallet. Use an Ethereum account that supports personal message signing.</p>
        </>}
      </>}
      {!connection && !error && <p role="status">Loading your private link…</p>}
      {error && <p className="err" role="alert">{error}</p>}
    </div>
  </section>
}
