import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { apiUrl } from './api.js'
import { canonicalLocation } from './privateRoutes.js'
import './styles.css'

// ink or paper: a stored choice beats the system setting (styles.css handles the rest)
try {
  const t = localStorage.getItem('protoss.theme') || 'light'
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t
} catch { /* private mode */ }

// Existing rich-share links still resolve through the backend's preview pages.
if (/^\/(t|h|l)\//.test(location.pathname)) location.replace(apiUrl(location.pathname) + location.search)

const redirect = canonicalLocation()
if (redirect) location.replace(redirect)
else createRoot(document.getElementById('root')).render(<App />)
