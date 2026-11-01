import React, { useEffect, useRef, useState } from 'react'
import { l1TypedData, splitSig } from './hlsign.js'
import Probe from './Probe.jsx'

const EXCHANGE = 'https://api.hyperliquid.xyz/exchange'
const money = (value) => '$' + Number(value).toFixed(2)

export default function TradeReview({ token }) {
  const [trade, setTrade] = useState(null)
  const [quote, setQuote] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [consent, setConsent] = useState(false)
  const [prepared, setPrepared] = useState(false)
  const [leverageReady, setLeverageReady] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const [clock, setClock] = useState(Date.now())
  const lock = useRef(false)
  const provider = () => window.protossWallet || window.ethereum

  async function api(path, body) {
    const response = await fetch('/live/' + path, { method: body === undefined ? 'GET' : 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      cache: 'no-store', body: body === undefined ? undefined : JSON.stringify(body) })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not complete this request.')
    return data
  }

  useEffect(() => {
    let alive = true
    if (!token) { setError('Open your private Review my trade link from the Telegram bot.'); return }
    api('review').then((data) => { if (alive) { setTrade(data); setQuote(data.quote) } })
      .catch((e) => { if (alive) setError(e.message) })
    const timer = setInterval(() => setClock(Date.now()), 1000)
    return () => { alive = false; clearInterval(timer) }
  }, [token])

  useEffect(() => {
    if (trade?.status !== 'prepared') return
    let alive = true
    const timer = setInterval(() => {
      api('verify', {}).then((data) => { if (alive) setTrade((current) => ({ ...current, ...data })) })
        .catch((e) => { if (alive) setError(e.message) })
    }, 5000)
    return () => { alive = false; clearInterval(timer) }
  }, [token, trade?.status])

  useEffect(() => {
    const walletProvider = provider()
    const changed = () => {
      setConsent(false)
      setError('Wallet selection changed. Switch back to the wallet shown on this request before continuing.')
    }
    walletProvider?.on?.('accountsChanged', changed)
    return () => walletProvider?.removeListener?.('accountsChanged', changed)
  }, [])

  async function run(fn) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { await fn() } catch (e) {
      setError(e.code === 4001 ? 'Wallet approval declined. Check the trade status before trying a new request.' : e.message)
    } finally { lock.current = false; setBusy(false) }
  }

  async function walletAccount(expected) {
    const p = provider()
    if (!p) throw new Error('Open this link in a browser with your wallet extension. Telegram’s built-in browser may not expose it.')
    const accounts = await p.request({ method: 'eth_requestAccounts' })
    if (!accounts[0] || (expected && accounts[0].toLowerCase() !== expected.toLowerCase())) {
      throw new Error('Select the exact wallet shown on this request.')
    }
    return { p, account: accounts[0] }
  }

  async function connect() {
    const { p, account } = await walletAccount()
    const hex = '0x' + Array.from(new TextEncoder().encode(trade.challenge), (b) => b.toString(16).padStart(2, '0')).join('')
    const signature = await p.request({ method: 'personal_sign', params: [hex, account] })
    const data = await api('wallet', { wallet: account, signature })
    setTrade((current) => ({ ...current, ...data }))
  }

  async function refreshQuote() {
    setConsent(false)
    setQuote(null)
    const data = await api('quote', {})
    setQuote(data)
    setNotice('Quote received from Hyperliquid. Review the amounts below.')
  }

  async function signAndSend(action, nonce, expiresAfter) {
    if (Date.now() >= expiresAfter - 3000) throw new Error('Quote expired. No new signature will be requested.')
    const { p, account } = await walletAccount(trade.wallet)
    const signature = await p.request({ method: 'eth_signTypedData_v4',
      params: [account, JSON.stringify(l1TypedData(action, nonce, true, expiresAfter))] })
    // Recheck after the wallet dialog: it can remain open beyond the quote expiry.
    const accounts = await p.request({ method: 'eth_accounts' })
    if (accounts[0]?.toLowerCase() !== trade.wallet.toLowerCase()) throw new Error('Wallet changed. Signed action was not submitted.')
    if (Date.now() >= expiresAfter) throw new Error('Quote expired while waiting. Signed action was not submitted.')
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 20000)
    try {
      const response = await fetch(EXCHANGE, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, nonce, expiresAfter, signature: splitSig(signature), vaultAddress: null }), signal: controller.signal })
      const data = await response.json()
      if (!response.ok || data.status !== 'ok') throw new Error(typeof data.response === 'string' ? data.response : 'Exchange did not confirm this action.')
      return data
    } catch (e) {
      throw new Error(`${e.message} Check exchange status before starting another request. This page will not resend automatically.`)
    } finally { clearTimeout(timer) }
  }

  async function setLeverage() {
    if (!consent || !quote) throw new Error('Review the quote and confirm the settings first.')
    let reviewed = quote
    if (!prepared) {
      reviewed = await api('prepare', { nonce: quote.nonce })
      // The server locks the same reviewed quote. Do not accept different order terms.
      if (JSON.stringify(reviewed) !== JSON.stringify(quote)) throw new Error('Quote changed. Reload and review the request.')
      setPrepared(true)
      setTrade((current) => ({ ...current, status: 'prepared' }))
    }
    await signAndSend(reviewed.leverage_action, reviewed.nonce, reviewed.expires_after)
    setLeverageReady(true)
    setNotice('Hyperliquid accepted the 1× cross-margin setting. The buy still needs your separate approval.')
  }

  async function buy() {
    if (!prepared || !leverageReady || !consent || attempted) throw new Error('Review and set 1× before approving this buy.')
    setAttempted(true) // one submission attempt per mounted page; reload never restores this action
    const result = await signAndSend(quote.order_action, quote.nonce + 1, quote.expires_after)
    const statuses = result.response?.data?.statuses || []
    const failure = statuses.find((s) => s.error)
    if (failure) throw new Error(failure.error)
    setNotice('Order submitted. Waiting for Hyperliquid fill verification. A submission is not a completed trade.')
    const data = await api('verify', {})
    setTrade((current) => ({ ...current, ...data }))
  }

  const remaining = quote ? Math.max(0, Math.floor((quote.expires_after - clock) / 1000)) : 0
  const receipt = trade?.receipt
  const active = trade?.status === 'draft' || prepared
  return <section className="trade-review">
    <div className="trade-heading"><Probe state={receipt ? 'success' : busy ? (prepared ? 'working' : 'thinking') : trade?.status === 'prepared' ? 'working' : 'idle'} />
      <div><span className="trade-network">Hyperliquid mainnet · real money</span><h1>Your idea. Your trade.</h1></div></div>
    <p className="sub">Each friend owns and approves their own position. Your wallet keeps control.</p>
    {!trade && !error && <p role="status">Loading your private request…</p>}
    {trade && <div className="card pad list">
      <div className="kv"><span>Participant</span><strong>{trade.participant} · {trade.telegram_user_id}</strong></div>
      <div className="kv"><span>Market</span><strong>Buy {trade.market}</strong></div>
      <div className="kv"><span>Maximum position value</span><strong>{money(trade.budget)} + exchange fees</strong></div>
      <p className="sub">{trade.market === 'xyz:ANT' ? 'Anthropic-linked perpetual. This does not buy shares.' : 'Perpetual contract. This does not buy the underlying coin.'} Funding charges and liquidation risk apply. No automatic exit or stop-loss is included.</p>
      <div className="trade-steps" aria-label="Trade progress"><span>1. Connect wallet</span><span>2. Review live quote</span><span>3. Approve in wallet</span><span>4. Verify fill</span></div>
      {!trade.wallet ? <>
        <button className="primary" disabled={busy} onClick={() => run(connect)}>Connect wallet and prove ownership</button>
        <p className="sub">This first signature proves ownership only. It cannot place a trade.</p>
      </> : <>
        <p className="addr">Your wallet: {trade.wallet}</p>
        {receipt ? <div className="notice"><h2>{trade.status === 'partial' ? 'Partial fill verified' : 'Trade verified'}</h2>
          <p>Bought {receipt.size} {receipt.market} at {money(receipt.average_price)}.</p>
          <p>Position value {money(receipt.position_value)}. Fees: {receipt.fees.map((f) => `${f.amount} ${f.token}`).join(', ')}.</p>
          <p>Hyperliquid order {receipt.order_id}. Your Telegram group receives this receipt too.</p>
        </div> : <>
          {trade.status === 'draft' && <button disabled={busy} onClick={() => run(refreshQuote)}>Get current quote</button>}
          {quote && <>
            <div className="kv"><span>Current ask</span><strong>{money(quote.ask)}</strong></div>
            <div className="kv"><span>Buy quantity</span><strong>{quote.size} {trade.market}</strong></div>
            <div className="kv"><span>Maximum buy price</span><strong>{quote.limit_price}</strong></div>
            <div className="kv"><span>Maximum position cost</span><strong>{money(quote.max_position_usd)}</strong></div>
            <div className="kv"><span>Quote expires in</span><strong>{remaining}s</strong></div>
            <p className="sub">Up to 0.5% above the current ask. Quantity is rounded down to stay within your budget. Any unfilled portion cancels immediately. {quote.fee_note}</p>
            {quote.account.mode === 'unifiedAccount' && <p className="notice">Unified account: Hyperliquid determines available collateral across your balances. The exchange can reject an order for insufficient margin.</p>}
            {active && <>
              <label className="trade-consent"><input type="checkbox" checked={consent} disabled={busy || attempted} onChange={(e) => setConsent(e.target.checked)} />
                <span>I reviewed this wallet and amount. I choose 1× cross margin for this market and understand this uses real money. Cross margin shares collateral within the exchange account.</span></label>
              {!leverageReady && <button disabled={busy || !consent || remaining < 15} onClick={() => run(setLeverage)}>1. Approve 1× setting in wallet</button>}
              {leverageReady && <button className="primary" disabled={busy || !consent || attempted || remaining < 4} onClick={() => run(buy)}>2. Approve buy up to {money(quote.max_position_usd)}</button>}
            </>}
          </>}
          {trade.status === 'prepared' && <><p className="notice">This request has been prepared. If you reloaded or lost the connection, check the result below and your Hyperliquid order history before creating another request. No automatic retry.</p>
            <button disabled={busy} onClick={() => run(async () => { const data = await api('verify', {}); setTrade((current) => ({ ...current, ...data })); setNotice(data.receipt ? 'Exchange fill verified.' : 'No fill verified yet. Check Hyperliquid order history; do not assume the order failed.') })}>Check exchange result</button></>}
        </>}
      </>}
      <a href="https://app.hyperliquid.xyz/trade" target="_blank" rel="noopener noreferrer">Open Hyperliquid to review funding, orders or close a position</a>
      {notice && <p role="status">{notice}</p>}
      {busy && <p role="status">Waiting for your wallet or exchange…</p>}
    </div>}
    {error && <p className="err" role="alert">{error}</p>}
  </section>
}
