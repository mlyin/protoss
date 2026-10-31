import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'

// ink or paper: a stored choice beats the system setting (styles.css handles the rest)
try {
  const t = localStorage.getItem('protoss.theme')
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t
} catch { /* private mode */ }

createRoot(document.getElementById('root')).render(<App />)
