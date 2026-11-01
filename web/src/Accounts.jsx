import React, { useEffect, useState } from 'react'
import { account } from './hlinfo.js'
import { TELEGRAM_BOT } from './ideas.js'
import { SkelLines } from './ui.jsx'

// The accounts the Telegram bot trades for (registered with scripts/wallets.py). Public addresses only;
// each account authorizes its own API wallet, and its orders leave from it.
export const ACCOUNTS = [
  { name: 'lando', address: '0x562B9081dF47193428a67b0885d9562eDE242c01' },
  { name: 'second', address: '0x027D9eEEe7eFc177b5287f7f5E0976b37ad838c9' },
]

const usd = (v) => (v == null ? '—' : (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
const px = (v) => (v == null ? '—' : Number(v).toLocaleString(undefined, { maximumSignificantDigits: 6 }))
const cls = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '')
const short = (a) => `${a.slice(0, 6)}…${a.slice(-4)}`
const explorer = (a) => `https://app.hyperliquid.xyz/explorer/address/${a}`
const when = (ms) => new Date(ms).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })

function useAccounts(ms = 15000) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    let alive = true
    const go = () => Promise.all(ACCOUNTS.map((a) => account(a.address).then((d) => ({ ...a, ...d }))))
      .then((d) => alive && (setData(d), setErr(null)))
      .catch((e) => alive && setErr(e.message))
    go()
    const id = setInterval(go, ms)
    return () => { alive = false; clearInterval(id) }
  }, [ms])
  return [data, err]
}

function AccountCard({ a }) {
  return (
    <section className="card acct">
      <div className="cardhead">
        <h2>{a.name}</h2>
        <a className="sub mono" href={explorer(a.address)} target="_blank" rel="noreferrer">{short(a.address)}</a>
        <span className="spacer" />
        <span className="sub">{a.unified ? 'unified account' : 'standard account'}</span>
      </div>
      <div className="statrow">
        <div><span className="label">Equity</span><span className="value">{usd(a.equity)}</span></div>
        <div><span className="label">Open positions</span><span className="value">{a.positions.length}</span></div>
        <div><span className="label">Unrealized P&amp;L</span><span className={`value ${cls(a.positions.reduce((s, p) => s + p.upnl, 0))}`}>{usd(a.positions.reduce((s, p) => s + p.upnl, 0))}</span></div>
        <div><span className="label">USDC</span><span className="value">{usd(a.unified ? a.usdc : a.perpValue + a.usdc)}</span><span className="sub">{a.unified ? 'spot, used as margin' : `${usd(a.perpValue)} perps, ${usd(a.usdc)} spot`}</span></div>
      </div>
      {a.positions.length === 0 ? (
        <div className="empty"><b>No open positions</b><span>When a trade from the group goes out from this account, it shows here.</span></div>
      ) : (
        <div className="tablewrap"><table className="mini">
          <thead><tr><th>Market</th><th>Side</th><th className="num">Size</th><th className="num">Entry</th><th className="num">Value</th><th className="num">Unrealized</th><th className="num">Leverage</th><th className="num">Liquidation</th></tr></thead>
          <tbody>{a.positions.map((p) => (
            <tr key={p.market}>
              <td className="text"><b>{p.market}</b></td>
              <td className={p.size > 0 ? 'pos' : 'neg'}>{p.size > 0 ? 'long' : 'short'}</td>
              <td className="num">{px(Math.abs(p.size))}</td>
              <td className="num">{px(p.entry)}</td>
              <td className="num">{usd(p.value)}</td>
              <td className={`num ${cls(p.upnl)}`}>{usd(p.upnl)}</td>
              <td className="num">{p.leverage ? `${p.leverage}×` : '—'}</td>
              <td className="num">{px(p.liq)}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </section>
  )
}

export default function Accounts() {
  const [data, err] = useAccounts()
  const fills = (data || []).flatMap((a) => a.fills.map((f) => ({ ...f, who: a.name }))).sort((x, y) => y.time - x.time).slice(0, 25)
  return (
    <section className="accounts">
      <div className="app-intro">
        <h1>Accounts</h1>
        <p>Live from Hyperliquid, refreshed every 15 seconds. These are the accounts the Telegram bot trades for; every order leaves from the account that approved it. Nothing here is simulated.</p>
        <div className="welcome-actions"><a className="btn primary" href={TELEGRAM_BOT} target="_blank" rel="noreferrer">Open Telegram</a><a className="btn" href="/app/#/lab">Test an idea</a></div>
      </div>
      {err && <div className="notice warn" role="alert">Could not reach Hyperliquid ({err}). Showing nothing rather than old or invented numbers.</div>}
      {!data && !err && <div className="card"><SkelLines n={5} /></div>}
      {data && data.map((a) => <AccountCard key={a.address} a={a} />)}
      {data && (
        <section className="card">
          <div className="cardhead"><h2>Recent fills</h2><span className="sub">both accounts, newest first, from Hyperliquid fill history</span></div>
          {fills.length === 0 ? <div className="empty"><b>No fills yet</b></div> : (
            <div className="tablewrap"><table className="mini">
              <thead><tr><th>When</th><th>Account</th><th>Market</th><th>Side</th><th className="num">Size</th><th className="num">Price</th><th className="num">Fee</th><th className="num">Closed P&amp;L</th></tr></thead>
              <tbody>{fills.map((f) => (
                <tr key={`${f.who}-${f.tid || f.hash}-${f.time}`}>
                  <td>{when(f.time)}</td>
                  <td className="text">{f.who}</td>
                  <td className="text"><b>{f.market}</b><span className="sub">{f.dir}</span></td>
                  <td className={f.side === 'B' ? 'pos' : 'neg'}>{f.side === 'B' ? 'buy' : 'sell'}</td>
                  <td className="num">{px(f.sz)}</td>
                  <td className="num">{px(f.px)}</td>
                  <td className="num">{px(f.fee)} {f.feeToken}</td>
                  <td className={`num ${cls(Number(f.closedPnl))}`}>{Number(f.closedPnl) ? usd(Number(f.closedPnl)) : '—'}</td>
                </tr>
              ))}</tbody>
            </table></div>
          )}
        </section>
      )}
    </section>
  )
}
