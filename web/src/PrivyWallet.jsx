import React, { useEffect } from 'react'
import { PrivyProvider, usePrivy, useWallets } from '@privy-io/react-auth'

// Email sign-in that makes the user a wallet only they control (Privy embedded wallet). Loaded lazily from Join.jsx,
// and only when the server reports a PRIVY_APP_ID, so the dashboard does not carry Privy's bundle otherwise.
// Sets window.protossWallet to the wallet's EIP-1193 provider; Join's Stake button signs vaultTransfer with it.

function Inner({ onAddress }) {
  const { ready, authenticated, login, logout } = usePrivy()
  const { wallets } = useWallets()
  const embedded = wallets.find((w) => w.walletClientType === 'privy')

  useEffect(() => {
    let alive = true
    if (!embedded) { window.protossWallet = undefined; return }
    embedded.getEthereumProvider().then((p) => {
      if (!alive) return
      window.protossWallet = p
      onAddress(embedded.address)
    })
    return () => { alive = false }
  }, [embedded?.address])

  if (!ready) return <button type="button" disabled>Loading</button>
  if (!authenticated) return <button type="button" onClick={login}>Sign in with email</button>
  return (
    <span className="sub">
      {embedded ? `Your wallet: ${embedded.address.slice(0, 6)}…${embedded.address.slice(-4)}` : 'Making your wallet'}
      {' · '}<button type="button" className="ghost" onClick={logout}>Sign out</button>
    </span>
  )
}

export default function PrivyWallet({ appId, onAddress }) {
  return (
    <PrivyProvider
      appId={appId}
      config={{
        loginMethods: ['email'],
        embeddedWallets: { ethereum: { createOnLogin: 'users-without-wallets' } },
        appearance: { theme: 'dark' },
      }}
    >
      <Inner onAddress={onAddress} />
    </PrivyProvider>
  )
}
