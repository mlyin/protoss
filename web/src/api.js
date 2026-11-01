// Public configuration only. Never place credentials in a VITE_ variable.
const configured = (import.meta.env.VITE_API_ORIGIN || (import.meta.env.PROD ? 'https://api.protoss.trade' : '')).replace(/\/$/, '')
if (configured) {
  const url = new URL(configured)
  const local = ['localhost', '127.0.0.1'].includes(url.hostname)
  if ((!local && url.protocol !== 'https:') || url.origin !== configured || url.username || url.password) {
    throw new Error('VITE_API_ORIGIN must be an HTTPS origin (HTTP is allowed only for localhost)')
  }
}
export const API_ORIGIN = configured
export function apiUrl(path) {
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('Expected an absolute API path')
  return `${API_ORIGIN}${path}`
}
export function apiFetch(path, options = {}) {
  // Hyperliquid calls retain their explicit destination and individual wallet approvals.
  const url = /^https:\/\//.test(path) ? path : apiUrl(path)
  return globalThis.fetch(url, { credentials: 'omit', ...options })
}
