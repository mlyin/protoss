// Tokens stay in the URL fragment. Never copy them into query strings or storage.
export function privateRoute(hash = location.hash) {
  const [path, query = ''] = hash.slice(1).split('?')
  if (path !== '/telegram/connect' && path !== '/trade') return null
  const params = new URLSearchParams(query)
  return { path, token: params.get('token') || '' }
}

export function canonicalLocation(current = location) {
  const { pathname, search, hash } = current
  if (pathname === '/app') return '/app/' + search + hash
  if (pathname.startsWith('/app/') && !['/app/', '/app/index.html'].includes(pathname)) return '/app/'
  // Only the two private account routes survive retirement of the old practice app.
  if (pathname === '/' && hash && hash !== '#/') return '/app/' + (privateRoute(hash) ? hash : '')
  if (pathname.startsWith('/app/') && hash && !privateRoute(hash)) return '/app/'
  return null
}
