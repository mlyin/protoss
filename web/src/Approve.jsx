import React, { useEffect, useState } from 'react'

// Approve the Coliseum builder fee from the visitor's own Hyperliquid wallet.
// Signs Hyperliquid's user-signed action `approveBuilderFee` (EIP-712, primary type
// HyperliquidTransaction:ApproveBuilderFee) with the injected wallet and posts it to the HL API.
// Typed-data layout verified byte-for-byte against hyperliquid-python-sdk's signer.

const ZERO = '0x0000000000000000000000000000000000000000'

function splitSig(sig) {
  const h = sig.startsWith('0x') ? sig.slice(2) : sig
  let v = parseInt(h.slice(128, 130), 16)
  if (v < 27) v += 27
  return { r: '0x' + h.slice(0, 64), s: '0x' + h.slice(64, 128), v }
}

export default function Approve() {
  const [b, setB] = useState(null)
  const [err, setErr] = useState(null)
  const [acct, setAcct] = useState(null)
  const [net, setNet] = useState(null)
  const [approved, setApproved] = useState(null)
  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState([])
  const say = (m) => setLog((l) => [...l, m])

  useEffect(() => {
    fetch('/builder').then((r) => r.json()).then((d) => { setB(d); setNet(d.network) }).catch((e) => setErr(String(e)))
  }, [])

  const api = () => (net === 'Testnet' ? 'https://api.hyperliquid-testnet.xyz' : 'https://api.hyperliquid.xyz')

  async function connect() {
    if (!window.ethereum) return setErr('No wallet found. Install Rabby or MetaMask, then reload.')
    const [a] = await window.ethereum.request({ method: 'eth_requestAccounts' })
    setAcct(a)
    await check(a)
  }

  async function check(a = acct) {
    if (!a || !b?.address) return
    const r = await fetch(api() + '/info', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ type: 'maxBuilderFee', user: a, builder: b.address }) })
    const n = Number(await r.json())
    setApproved(Number.isFinite(n) ? n : 0)
  }

  async function approve() {
    setErr(null); setBusy(true)
    try {
      const chainHex = await window.ethereum.request({ method: 'eth_chainId' }) // any chain works; it only scopes the signature
      const nonce = Date.now()
      const message = { hyperliquidChain: net, maxFeeRate: b.fee_pct, builder: b.address, nonce }
      const typed = {
        domain: { name: 'HyperliquidSignTransaction', version: '1', chainId: parseInt(chainHex, 16), verifyingContract: ZERO },
        types: {
          EIP712Domain: [{ name: 'name', type: 'string' }, { name: 'version', type: 'string' }, { name: 'chainId', type: 'uint256' }, { name: 'verifyingContract', type: 'address' }],
          'HyperliquidTransaction:ApproveBuilderFee': [{ name: 'hyperliquidChain', type: 'string' }, { name: 'maxFeeRate', type: 'string' }, { name: 'builder', type: 'address' }, { name: 'nonce', type: 'uint64' }],
        },
        primaryType: 'HyperliquidTransaction:ApproveBuilderFee',
        message,
      }
      say(`signing approval of ${b.fee_pct} for ${b.address} on ${net}…`)
      const sig = await window.ethereum.request({ method: 'eth_signTypedData_v4', params: [acct, JSON.stringify(typed)] })
      const body = { action: { type: 'approveBuilderFee', hyperliquidChain: net, signatureChainId: chainHex, maxFeeRate: b.fee_pct, builder: b.address, nonce }, nonce, signature: splitSig(sig) }
      const r = await fetch(api() + '/exchange', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
      const j = await r.json()
      say(JSON.stringify(j))
      if (j.status !== 'ok') throw new Error(j.response || JSON.stringify(j))
      await check()
      say('done — your orders routed through Coliseum now carry its builder code')
    } catch (e) {
      setErr(e?.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  const want = b?.fee_tenths_bp ?? 0
  const ok = approved != null && approved >= want

  return (
    <section className="card approve pad">
      <div className="cardhead"><h2>Approve the Coliseum builder fee</h2></div>
      {!b ? <div className="sub">loading…</div> : (
        <>
          <p>Coliseum routes every agent order through its own Hyperliquid <b>builder code</b> and charges <b>{b.fee_pct}</b> of notional per fill ({b.fee_tenths_bp} tenths of a bp; the protocol cap is 0.1% on perps). If your agent trades from <i>your</i> Hyperliquid wallet, approve it once below. Coliseum's own master wallet is already approved for every phalanx.</p>
          <dl className="kvd">
            <dt>builder</dt><dd><code>{b.address || 'not configured (HL_BUILDER_ADDRESS)'}</code></dd>
            <dt>max fee</dt><dd>{b.fee_pct}</dd>
            <dt>network</dt><dd>
              <span className="seg">{['Mainnet', 'Testnet'].map((n) => <button key={n} className={net === n ? 'on' : ''} onClick={() => { setNet(n); setApproved(null) }}>{n}</button>)}</span>
            </dd>
            {acct && <><dt>wallet</dt><dd><code>{acct}</code></dd></>}
            {approved != null && <><dt>approved</dt><dd className={ok ? 'pos' : 'neg'}>{(approved / 1000).toFixed(3)}% {ok ? '— sufficient' : '— needs approval'}</dd></>}
          </dl>
          {b.warning && <div className="err">{b.warning}</div>}
          <div className="actions">
            {!acct ? <button className="primary" onClick={connect}>Connect wallet</button> : (
              <>
                <button className="primary" disabled={busy || ok || !b.address} onClick={approve}>{ok ? 'Approved' : busy ? 'Waiting for wallet…' : `Approve ${b.fee_pct}`}</button>
                <button onClick={() => check()} disabled={busy}>Re-check</button>
              </>
            )}
          </div>
          <p className="sub">The signature is a Hyperliquid user-signed action (<code>approveBuilderFee</code>), sent straight from your browser to <code>{api()}</code>. It must come from your main wallet, not an agent/API wallet. You can revoke it any time in the Hyperliquid app under Settings → Builder fees.</p>
          {err && <div className="err">{err}</div>}
          {log.length > 0 && <pre className="logbox">{log.join('\n')}</pre>}
        </>
      )}
    </section>
  )
}
