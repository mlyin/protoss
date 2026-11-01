import React, { useState } from 'react'

const methods = [
  { id: 'card', name: 'Card or Apple Pay', mark: '01', detail: 'Use a debit card or a payment wallet.', action: 'Preview checkout', steps: ['Review the provider quote', 'Confirm payment with the provider', 'Receive USDC in your wallet'], setup: 'Provider approval, signed checkout and verified settlement are required before live payments.' },
  { id: 'cash', name: 'Cash App', mark: '02', detail: 'Pay from your Cash App balance, where available.', action: 'Preview Cash App', steps: ['Check payment eligibility', 'Authorize with Cash App through the provider', 'Receive USDC in your wallet'], setup: 'Cash App availability must be confirmed for our MoonPay integration and your region.' },
  { id: 'crypto', name: 'Send crypto', mark: '03', detail: 'Transfer from a wallet or an exchange.', action: 'Preview transfer', steps: ['Choose the token and network', 'Get a deposit address and QR code', 'Track conversion and arrival'], setup: 'Multi-chain deposit routing is not connected yet. No real deposit address is issued in this demo.' },
  { id: 'wallet', name: 'Connect a wallet', mark: '04', detail: 'Use crypto you already hold in a wallet.', action: 'Preview wallet connection', steps: ['Choose your wallet', 'Review the network and transfer', 'Approve the transfer in your wallet'], setup: 'Wallet connection, network checks and routing must be verified before live transfers.' },
  { id: 'coinbase', name: 'Coinbase', mark: '05', detail: 'Use your Coinbase balance or buy USDC.', action: 'Preview Coinbase', steps: ['Continue to Coinbase', 'Choose an available balance or payment method', 'Confirm delivery to your wallet'], setup: 'Coinbase secure session tokens and settlement tracking are required. Other exchanges use Send crypto.' },
]
const money = (n) => Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })

// A local rehearsal only: no wallet requests, payment URLs, deposit addresses or ledger writes.
export default function FundingDemo({ orgs, preset }) {
  const [legion, setLegion] = useState(preset || '')
  const [amount, setAmount] = useState('20')
  const [method, setMethod] = useState('card')
  const [step, setStep] = useState(0)
  const [network, setNetwork] = useState('Arbitrum')
  const [token, setToken] = useState('USDC')
  const selected = methods.find((m) => m.id === method)
  const org = orgs.find((o) => o.slug === legion)
  const valid = Number.isFinite(Number(amount)) && Number(amount) >= 20 && Number(amount) <= 1000000
  const reset = () => setStep(0)

  return <section className="funding-page">
    <header className="funding-heading">
      <span className="funding-kicker">Bring your people. Test your idea.</span>
      <h1>A little each.<br />An idea together.</h1>
      <p>Choose a contribution and see how you would fund it.</p>
      <span className="funding-demo-label">Paper demo · no money moves</span>
    </header>
    <div className="funding-layout">
      <div className="funding-main">
        <div className="funding-section">
          <label htmlFor="funding-legion">Your legion</label>
          <select id="funding-legion" value={legion} onChange={(e) => { setLegion(e.target.value); reset() }}>
            <option value="">Demo legion</option>
            {orgs.map((o) => <option value={o.slug} key={o.slug}>{o.name}</option>)}
          </select>
        </div>
        <div className="funding-section">
          <h2>Your contribution</h2>
          <div className="funding-amounts">
            {[20, 50, 100].map((n) => <button type="button" key={n} aria-pressed={Number(amount) === n} className={Number(amount) === n ? 'selected' : ''} onClick={() => { setAmount(String(n)); reset() }}>${n}</button>)}
            <label className="funding-custom">$<input aria-label="Custom contribution" type="number" min="20" max="1000000" placeholder="Custom" value={[20, 50, 100].includes(Number(amount)) ? '' : amount} onChange={(e) => { setAmount(e.target.value); reset() }} /></label>
          </div>
          {!valid && <p className="err">Choose an amount from $20 to $1,000,000.</p>}
        </div>
        <div className="funding-section">
          <h2>How would you add funds?</h2>
          <div className="funding-methods" role="group" aria-label="Funding method">
            {methods.map((m) => <button type="button" key={m.id} className={`funding-method ${method === m.id ? 'selected' : ''}`} aria-pressed={method === m.id} onClick={() => { setMethod(m.id); reset() }}>
              <span className="funding-number">{m.mark}</span><span><strong>{m.name}</strong><small>{m.detail}</small></span><span aria-hidden="true">↗</span>
            </button>)}
          </div>
        </div>
      </div>
      <aside className="funding-summary" aria-live="polite">
        <span className="funding-kicker">{org?.name || 'Demo legion'}</span>
        <div className="funding-total">{valid ? money(amount) : '$0'}</div>
        <p className="sub">Your paper contribution</p>
        <div className="funding-divider" />
        {step === 0 && <>
          <h2>{selected.name}</h2>
          <p className="sub">Preview the steps before you commit.</p>
          <button className="primary" disabled={!valid} onClick={() => setStep(1)}>{selected.action}</button>
        </>}
        {step === 1 && <>
          <h2>Preview your funding</h2>
          {method === 'crypto' && <div className="funding-transfer">
            <label>Token<select value={token} onChange={(e) => setToken(e.target.value)}><option>USDC</option><option>ETH</option></select></label>
            <label>Network<select value={network} onChange={(e) => setNetwork(e.target.value)}><option>Arbitrum</option><option>Base</option><option>Ethereum</option></select></label>
          </div>}
          <ol className="funding-steps">{selected.steps.map((s) => <li key={s}>{s}</li>)}<li>Approve your contribution to the legion</li></ol>
          <p className="sub">{method === 'crypto' ? `${token} on ${network}. ` : ''}Live fees, minimums and the amount received will come from the provider quote.</p>
          <button className="primary" onClick={() => setStep(2)}>Simulate funds arriving</button>
        </>}
        {step === 2 && <>
          <h2>Paper funds received</h2>
          <p>{money(amount)} in your demo wallet. You approve the legion contribution as a separate step.</p>
          <button className="primary" onClick={() => setStep(3)}>Confirm paper contribution</button>
        </>}
        {step === 3 && <>
          <h2>Preview complete</h2>
          <p>{money(amount)} contributed in this preview. No wallet balance or legion ledger was changed.</p>
          <a className="btn primary" href="/app/#/huddle/paper20-20261031">Try the group chat</a>
        </>}
        {step > 0 && <button className="ghost" onClick={reset}>Start again</button>}
        <p className="funding-caption">Demo only. No card details, wallet signatures or exchange login required.</p>
        <details className="funding-readiness"><summary>Live availability</summary><p>{selected.setup}</p><p>Funding goes to your wallet first. Builder fees apply to eligible trading orders, not deposits. Live contributions remain off.</p></details>
      </aside>
    </div>
  </section>
}
