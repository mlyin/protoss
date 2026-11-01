import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { apiUrl } from './api.js'
import './styles.css'

// ink or paper: a stored choice beats the system setting (styles.css handles the rest)
try {
  const t = localStorage.getItem('protoss.theme') || 'light'
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t
} catch { /* private mode */ }

// Existing rich-share links still resolve through the backend's preview pages.
if (/^\/(t|h|l)\//.test(location.pathname)) location.replace(apiUrl(location.pathname) + location.search)

// Canonical URLs use /app/#/... so refreshes work on static hosting.
if (location.pathname === '/app') location.replace('/app/' + location.search + location.hash)
if (location.pathname.startsWith('/app/') && location.pathname !== '/app/' && location.pathname !== '/app/index.html') {
  location.replace('/app/#/' + location.pathname.slice(5) + location.search)
}
// Preserve old shared hash links while giving the app a stable Pages entrypoint.
if (location.pathname === '/' && location.hash && location.hash !== '#/') {
  location.replace('/app/' + location.search + location.hash)
}

createRoot(document.getElementById('root')).render(<App />)
