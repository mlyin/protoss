import { keccak_256 } from '@noble/hashes/sha3'

// Hyperliquid L1 action signing in the browser, for `vaultTransfer` (staking into and leaving a legion's vault).
// Mirrors hyperliquid-python-sdk's signing.py: action_hash = keccak(msgpack(action) || nonce u64 BE || 0x00),
// signed as the EIP-712 "phantom agent" {source: "a"|"b", connectionId: hash} under domain Exchange/1/1337.
// Verified byte-for-byte against the Python SDK on 2026-10-31 (same action, nonce and key, same r/s/v).
// The user's own wallet signs; Protoss never sees the key.

const ZERO = '0x0000000000000000000000000000000000000000'
const enc = new TextEncoder()

// The subset of msgpack the SDK's packb emits for these actions: maps, strings, bools, unsigned ints.
function pack(v, out) {
  if (Array.isArray(v)) {
    if (v.length >= 16) throw new Error('array too large')
    out.push(0x90 | v.length)
    for (const item of v) pack(item, out)
    return
  }
  if (typeof v === 'boolean') { out.push(v ? 0xc3 : 0xc2); return }
  if (typeof v === 'number') {
    if (!Number.isSafeInteger(v) || v < 0) throw new Error('only unsigned integers are packed')
    if (v < 0x80) out.push(v)
    else if (v < 0x100) out.push(0xcc, v)
    else if (v < 0x10000) out.push(0xcd, v >> 8, v & 0xff)
    else if (v < 0x100000000) out.push(0xce, (v >>> 24) & 0xff, (v >>> 16) & 0xff, (v >>> 8) & 0xff, v & 0xff)
    else { out.push(0xcf); be64(BigInt(v), out) }
    return
  }
  if (typeof v === 'string') {
    const b = enc.encode(v)
    if (b.length < 32) out.push(0xa0 | b.length)
    else if (b.length < 0x100) out.push(0xd9, b.length)
    else out.push(0xda, b.length >> 8, b.length & 0xff)
    out.push(...b)
    return
  }
  if (v && typeof v === 'object') {
    const keys = Object.keys(v)
    if (keys.length >= 16) throw new Error('map too large')
    out.push(0x80 | keys.length)
    for (const k of keys) { pack(k, out); pack(v[k], out) }
    return
  }
  throw new Error(`cannot pack ${typeof v}`)
}

function be64(n, out) { for (let i = 7; i >= 0; i--) out.push(Number((n >> BigInt(i * 8)) & 0xffn)) }

const hex = (bytes) => '0x' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')

export function actionHash(action, nonce, expiresAfter = null) {
  const out = []
  pack(action, out)
  be64(BigInt(nonce), out)
  out.push(0x00) // no vaultAddress on the envelope: the user signs for their own account
  if (expiresAfter !== null) { out.push(0x00); be64(BigInt(expiresAfter), out) }
  return hex(keccak_256(Uint8Array.from(out)))
}

export function vaultTransferAction(vault, usd, isDeposit = true) {
  // usd is in micro-USDC (6 decimals), as an integer, like the SDK's vault_usd_transfer
  return { type: 'vaultTransfer', vaultAddress: vault.toLowerCase(), isDeposit, usd: Math.round(usd * 1e6) }
}

export function l1TypedData(action, nonce, mainnet, expiresAfter = null) {
  return {
    domain: { chainId: 1337, name: 'Exchange', verifyingContract: ZERO, version: '1' },
    types: {
      EIP712Domain: [{ name: 'name', type: 'string' }, { name: 'version', type: 'string' }, { name: 'chainId', type: 'uint256' }, { name: 'verifyingContract', type: 'address' }],
      Agent: [{ name: 'source', type: 'string' }, { name: 'connectionId', type: 'bytes32' }],
    },
    primaryType: 'Agent',
    message: { source: mainnet ? 'a' : 'b', connectionId: actionHash(action, nonce, expiresAfter) },
  }
}

export function splitSig(sig) {
  const h = sig.startsWith('0x') ? sig.slice(2) : sig
  let v = parseInt(h.slice(128, 130), 16)
  if (v < 27) v += 27
  return { r: '0x' + h.slice(0, 64), s: '0x' + h.slice(64, 128), v }
}

// Sign and post a vaultTransfer with any EIP-1193 provider (Privy's embedded wallet, or an injected one that
// allows signing for chain 1337). Returns Hyperliquid's response; throws on a refusal.
export async function stakeInVault(provider, { account, vault, usd, mainnet = true, isDeposit = true }) {
  const nonce = Date.now()
  const action = vaultTransferAction(vault, usd, isDeposit)
  const sig = await provider.request({ method: 'eth_signTypedData_v4', params: [account, JSON.stringify(l1TypedData(action, nonce, mainnet))] })
  const api = mainnet ? 'https://api.hyperliquid.xyz' : 'https://api.hyperliquid-testnet.xyz'
  const r = await fetch(api + '/exchange', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ action, nonce, signature: splitSig(sig), vaultAddress: null }) })
  const j = await r.json()
  if (j.status !== 'ok') throw new Error(typeof j.response === 'string' ? j.response : JSON.stringify(j))
  return j
}
