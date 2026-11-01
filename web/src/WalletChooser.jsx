import React, { useEffect, useState } from 'react'
import './WalletChooser.css'

function walletName(provider) {
  if (provider.isPhantom) return 'Phantom'
  if (provider.isRabby) return 'Rabby'
  if (provider.isCoinbaseWallet) return 'Coinbase Wallet'
  if (provider.isMetaMask) return 'MetaMask'
  return 'Browser wallet'
}

export default function WalletChooser({ onSelect, onCancel, busy = false }) {
  const [wallets, setWallets] = useState([])
  const [email, setEmail] = useState(false)
  useEffect(() => {
    let active = true
    const found = []
    const add = (provider, name) => {
      if (!active || !provider || typeof provider.request !== 'function') return
      const existing = found.find(item => item.provider === provider)
      if (existing) { if (name) existing.name = name }
      else found.push({ provider, name: name || walletName(provider), id: found.length })
      setWallets(found.map(item => ({ ...item })))
    }
    const announce = event => {
      const detail = event.detail
      const name = typeof detail?.info?.name === 'string' ? detail.info.name.trim().slice(0, 60) : ''
      add(detail?.provider, name)
    }
    window.addEventListener('eip6963:announceProvider', announce)
    window.dispatchEvent(new Event('eip6963:requestProvider'))
    // Older extensions may expose a provider list or only a single injected provider.
    const legacy = Array.isArray(window.ethereum?.providers) ? window.ethereum.providers : [window.ethereum]
    for (const provider of legacy) add(provider)
    add(window.phantom?.ethereum, 'Phantom')
    return () => { active = false; window.removeEventListener('eip6963:announceProvider', announce) }
  }, [])

  return <div className="wallet-chooser" role="group" aria-label="Choose your Hyperliquid wallet">
    <p>Choose the wallet you use on Hyperliquid.</p>
    <div className="wallet-options">{wallets.map(wallet => <button type="button" key={wallet.id}
      disabled={busy} onClick={() => onSelect(wallet.provider)}>{wallet.name}</button>)}</div>
    {!wallets.length && <p className="wallet-help">No browser wallet found. Open this page in the wallet you use on Hyperliquid, or enable its browser extension.</p>}
    <button type="button" className="wallet-help-toggle" onClick={() => setEmail(!email)} aria-expanded={email}>I use email on Hyperliquid</button>
    {email && <p className="wallet-help">Your Hyperliquid email wallet is separate from your browser wallets. Direct email-wallet connection is not available here yet. <a href="https://app.hyperliquid.xyz/" target="_blank" rel="noreferrer">Open Hyperliquid</a> to access that account.</p>}
    {busy && <p role="status">Waiting for the wallet you selected…</p>}
    <button type="button" className="wallet-help-toggle" onClick={onCancel}>Cancel</button>
  </div>
}
