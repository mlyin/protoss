import React, { useEffect, useState } from 'react'
import Homepage from './Homepage.jsx'
import AccountWorkspace from './AccountWorkspace.jsx'

export default function App() {
  const landing = !location.pathname.startsWith('/app')
  useEffect(() => {
    const clean = () => {
      if (location.pathname.startsWith('/app/') && location.hash) history.replaceState(null, '', '/app/')
      else if (location.pathname === '/' && location.hash.startsWith('#/')) location.replace('/app/')
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
    <main className="page">{landing ? <Homepage /> : <AccountWorkspace />}</main>
    <footer className="site-footer"><span>Protoss · Your friends. Your positions.</span><span>Positions from Hyperliquid · Read-only</span></footer>
  </>
}
