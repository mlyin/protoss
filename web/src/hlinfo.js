// Read-only Hyperliquid info API, straight from the browser (it allows any origin). No keys, no signing.
// Everything on the Accounts page comes from here, so nothing on it is simulated.

const INFO = 'https://api.hyperliquid.xyz/info'

export async function info(body) {
  const r = await fetch(INFO, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`Hyperliquid ${r.status}`)
  return r.json()
}

let dexsOnce = null
const dexs = () => (dexsOnce ||= info({ type: 'perpDexs' }).then((list) => list.map((d) => (d ? d.name : ''))))
let spotNamesOnce = null
// '@142' -> 'UBTC': spot fills name the pair by index; the base token's name is what a person reads
const spotNames = () => (spotNamesOnce ||= info({ type: 'spotMeta' }).then((m) => Object.fromEntries(m.universe.map((u) => [u.name, m.tokens[u.tokens[0]]?.name || u.name]))))

export async function account(address) {
  const [names, list] = await Promise.all([spotNames(), dexs()])
  const [mode, spot, fills, ...perps] = await Promise.all([
    info({ type: 'userAbstraction', user: address }),
    info({ type: 'spotClearinghouseState', user: address }),
    info({ type: 'userFills', user: address }),
    ...list.map((dex) => info({ type: 'clearinghouseState', user: address, dex })),
  ])
  const positions = perps.flatMap((s) => s.assetPositions.map((p) => p.position)).map((p) => ({
    market: p.coin, size: Number(p.szi), entry: Number(p.entryPx), value: Number(p.positionValue), upnl: Number(p.unrealizedPnl),
    leverage: p.leverage?.value, liq: p.liquidationPx ? Number(p.liquidationPx) : null,
  }))
  const usdc = Number(spot.balances.find((b) => b.coin === 'USDC')?.total || 0)
  const perpValue = perps.reduce((s, x) => s + Number(x.marginSummary.accountValue), 0)
  // unified accounts keep collateral as spot USDC (perps accountValue reads 0); standard accounts keep the two apart
  const unified = mode === 'unifiedAccount'
  const equity = unified ? usdc + positions.reduce((s, p) => s + p.upnl, 0) : perpValue + usdc
  const other = spot.balances.filter((b) => b.coin !== 'USDC' && Number(b.total) > 0).map((b) => ({ coin: b.coin, total: Number(b.total) }))
  return {
    address, unified, equity, usdc, perpValue, positions, spot: other,
    fills: fills.map((f) => ({ ...f, market: f.coin.startsWith('@') ? `${names[f.coin] || f.coin} spot` : f.coin })),
  }
}
