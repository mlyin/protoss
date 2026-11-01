import React, { lazy, Suspense, useEffect, useState } from 'react'
import Homepage from './Homepage.jsx'
import AccountWorkspace from './AccountWorkspace.jsx'
import { canonicalLocation, privateRoute } from './privateRoutes.js'

const TelegramConnect = lazy(() => import('./TelegramConnect.jsx'))
const TradeReview = lazy(() => import('./TradeReview.jsx'))

export default function App() {
  const landing = !location.pathname.startsWith('/app')
  const [route, setRoute] = useState(() => privateRoute())
  useEffect(() => {
    const clean = () => {
      const redirect = canonicalLocation()
      if (redirect) { location.replace(redirect); return }
      setRoute(privateRoute())
    }
    clean(); window.addEventListener('hashchange', clean)
    return () => window.removeEventListener('hashchange', clean)
  }, [])
  const [theme, setTheme] = useState(document.documentElement.dataset.theme || 'light')
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('protoss.theme', theme) } catch { /* browser storage is optional */ }
  }, [theme])
  return <>
    <header className="header"><div className="header-in">
      <a className="brand" href="/" aria-label="Protoss, home"><img src="/probe/idle.svg" alt="" /><span className="word">Protoss</span></a>
      <nav className="nav" aria-label="Main"><a className={landing ? 'on' : ''} href="/">Home</a><a className={!landing ? 'on' : ''} href="/app/">Friends &amp; positions</a></nav>
      <span className="spacer" /><a className="text-link" href="https://t.me/ProtossTradingDemoBot" target="_blank" rel="noreferrer">Telegram ↗</a>
      <button className="icon-btn" aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`} onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>◐</button>
    </div></header>
    <main className="page"><Suspense fallback={<p role="status">Opening your private link…</p>}>
      {route?.path === '/telegram/connect' ? <TelegramConnect key={route.path + route.token} token={route.token} />
        : route?.path === '/trade' ? <TradeReview key={route.path + route.token} token={route.token} />
          : landing ? <Homepage /> : <AccountWorkspace />}
    </Suspense></main>
    <footer className="site-footer"><span>Protoss · Your friends. Your positions.</span><span>{route?.path === '/trade' ? 'Each trade requires your wallet approval' : route ? 'Wallet ownership only · No trading permission' : 'Positions from Hyperliquid · Read-only'}</span></footer>
  </>
}
