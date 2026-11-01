import { apiUrl } from './api.js'
import React, { useEffect, useState } from 'react'
import Accounts from './Accounts.jsx'
import Approve from './Approve.jsx'
import Lab from './Lab.jsx'
import Homepage from './Homepage.jsx'
import { TELEGRAM_BOT } from './ideas.js'

function useHash() {
  const [h, setH] = useState(() => globalThis.location.hash || '#/')
  useEffect(() => {
    const on = () => setH(globalThis.location.hash || '#/')
    globalThis.addEventListener('hashchange', on)
    return () => globalThis.removeEventListener('hashchange', on)
  }, [])
  return h
}

function Mark() {
  return <img src="/favicon.svg" alt="" onError={(e) => { e.currentTarget.style.display = 'none' }} />
}

export function applyTheme(t) {
  const el = document.documentElement
  if (t === 'light' || t === 'dark') el.dataset.theme = t
  else delete el.dataset.theme
}

function ThemeToggle() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || (globalThis.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'))
  const flip = () => {
    const t = theme === 'light' ? 'dark' : 'light'
    setTheme(t)
    applyTheme(t)
    try { localStorage.setItem('protoss.theme', t) } catch { /* private mode */ }
  }
  const label = theme === 'light' ? 'Switch to ink' : 'Switch to paper'
  return (
    <button className="icon-btn" onClick={flip} aria-label={label} title={label}>
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
        <circle cx="10" cy="10" r="7.25" />
        <path d="M10 2.75v14.5a7.25 7.25 0 0 0 0-14.5Z" fill="currentColor" stroke="none" />
      </svg>
    </button>
  )
}

export default function App() {
  const hash = useHash()
  const landing = !location.pathname.startsWith('/app')
  const [route, qs] = hash.split('?')
  const query = new URLSearchParams(qs || '')
  // Old links (#/feed, #/huddle/..., #/p/...) land on the accounts page: the practice screens are gone.
  const page = route.startsWith('#/lab') ? 'lab' : route.startsWith('#/approve') ? 'approve' : 'accounts'
  const is = (p) => (!landing && page === p ? 'on' : '')

  return (
    <>
      <header className="header">
        <div className="header-in">
          <a className="brand" href="/" aria-label="Protoss, home"><Mark /><span className="word">Protoss</span></a>
          <nav className="nav" aria-label="Main">
            <a className={landing ? 'on' : ''} href="/">Home</a>
            <a className={is('lab')} href="/app/#/lab">Test an idea</a>
            <a className={is('accounts')} href="/app/#/accounts">Accounts</a>
          </nav>
          <span className="spacer" />
          <div className="header-right">
            <a className="btn sm primary" href={TELEGRAM_BOT} target="_blank" rel="noreferrer">Open Telegram</a>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="page">
        {landing ? <Homepage /> : <>
        {page === 'accounts' && <Accounts />}
        {page === 'lab' && <Lab initialPrompt={query.get('idea') || ''} autorun={query.get('run') === '1'} />}
        {page === 'approve' && <div className="one"><Approve /><a className="back" href="/app/#/accounts">Back to accounts</a></div>}
        </>}
      </main>
      <footer className="site-footer"><span>Protoss · Ideas from the group chat, traded for real</span><a href={TELEGRAM_BOT}>Telegram bot</a><a href="/app/#/approve">Trading fee settings</a><a href={apiUrl('/docs')}>Developer API</a></footer>
    </>
  )
}
