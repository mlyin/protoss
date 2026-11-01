import React, { useEffect, useState } from 'react'
import Probe, { ProbeConversation } from './Probe.jsx'

const PEOPLE = ['You', 'Your friend']
const money = (v) => '$' + Number(v || 0).toFixed(2)
const IDEAS = [
  { name: 'Crypto starter', text: 'Buy and hold 60% BTC and 40% ETH', detail: '60% Bitcoin · 40% Ethereum' },
  { name: 'Bitcoin only', text: 'Buy and hold BTC', detail: '100% Bitcoin' },
  { name: 'Anthropic example', text: 'Buy and hold Anthropic', detail: '100% xyz:ANT' },
]

export default function Demo({ room }) {
  const [roomId] = useState(() => /^[a-z0-9-]{1,28}$/.test(room || '') ? room : crypto.randomUUID().replaceAll('-', '').slice(0, 24))
  const [data, setData] = useState(null)
  const [person, setPerson] = useState(PEOPLE[0])
  const [idea, setIdea] = useState(IDEAS[0].text)
  const [amount, setAmount] = useState(20)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  async function load() {
    const response = await fetch(`/huddle/web/copies-${roomId}`)
    if (!response.ok) throw new Error('Could not open the demo. Check that the API is running.')
    return response.json()
  }
  useEffect(() => {
    let alive = true
    if (!room) window.history.replaceState(null, '', `#/demo?room=${roomId}`)
    const refresh = () => load().then((next) => { if (alive) setData(next) }).catch((e) => { if (alive) setError(e.message) })
    refresh()
    const timer = setInterval(refresh, 2500)
    return () => { alive = false; clearInterval(timer) }
  }, [roomId])
  async function send(text) {
    if (!data || busy) return
    setBusy(true); setError('')
    try {
      const response = await fetch(`/huddle/${data.id}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sender: person, text, guid: `demo:${crypto.randomUUID()}` }) })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not record this step. Try again.')
      const next = await load()
      setData(next)
      if (!next.theses.length) setError('The idea could not be tested. Try “Buy and hold Anthropic” or “Buy and hold BTC”.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const parent = data?.theses[0]
  const copies = (data?.theses || []).filter((item) => item.agent_id)
  const holdings = parent?.proposal?.holdings || []
  const completeCopies = copies.filter((item) => holdings.length > 0 && item.triggers.length === holdings.length)
  const mine = parent?.backers.find((backer) => backer.who === person)
  const confirmed = parent?.backers.filter((backer) => backer.approved && backer.pledge_usd > 0) || []
  const demoMode = data && ['sim', 'paper'].includes(data.mode)
  const ready = Number.isFinite(amount) && amount > 0 && amount <= 1000
  const progress = !parent ? 1 : completeCopies.length === 2 ? 4 : confirmed.length === 0 ? 2 : 3
  return <section className="browser-demo">
    <div className="demo-heading"><div><span className="sub">Protoss · interactive demo</span><h1>One idea. Your own trade.</h1><p>Try both sides of a trade with a friend. Each person chooses their amount and gets a separate practice trade.</p></div>
      <button onClick={async () => { try { await navigator.clipboard.writeText(window.location.href); setCopied(true) } catch { setError('Copy the address from your browser to share this demo.') } }}>{copied ? 'Demo link copied' : 'Share this demo'}</button>
    </div>
    <div className="demo-notice">Practice money only. No wallet, deposit or real trade is needed. These two names are demo roles, not verified accounts. {data?.mode === 'sim' ? 'Prices and results are simulated.' : 'Paper trades use market data when available.'} The demo uses perpetual markets, not ownership of coins or shares.</div>
    <ol className="demo-progress" aria-label="Demo steps">{['Share an idea', 'Choose your amount', 'Friend chooses theirs', 'See both trades'].map((label, i) => <li key={label} aria-current={progress === i + 1 ? 'step' : undefined}><span>{i + 1}</span>{label}</li>)}</ol>
    {data && !demoMode && <p className="err" role="alert">This server uses real accounts. Run the practice demo on a sim or paper host. No trading controls are enabled here.</p>}
    <div className="demo-columns">
      <div className="demo-workspace card pad">
        <div className="demo-person"><span>Try the demo as</span><div role="group" aria-label="Demo participant">{PEOPLE.map((name) => <button key={name} aria-pressed={person === name} onClick={() => setPerson(name)} disabled={busy}>{name}</button>)}</div></div>
        {!data && !error && <p role="status">Opening your practice room…</p>}
        {!parent ? <form onSubmit={(event) => { event.preventDefault(); send(`protoss ${idea}`) }}><div className="demo-templates" role="group" aria-label="Example ideas">{IDEAS.map((example) => <button key={example.name} type="button" aria-pressed={idea === example.text} onClick={() => setIdea(example.text)} disabled={busy}><strong>{example.name}</strong><span>{example.detail}</span></button>)}</div><label className="demo-label">What would you like to trade?<input value={idea} onChange={(event) => setIdea(event.target.value)} required maxLength={240} /></label><p className="sub">Pick an example or describe your own idea. Example splits are demo templates, not personalized recommendations.</p><button className="primary" disabled={busy || !demoMode || !idea.trim()}>{busy ? 'Testing your idea…' : 'Next: test this idea'}</button></form>
          : <>
            <span className="sub">The idea from {parent.author}</span><h2 className="demo-idea">{parent.label}</h2>
            <div className="demo-allocation"><h3>Your proposed split</h3>{holdings.map((holding) => <div className="kv" key={holding.market}><span>{holding.market}</span><span>{(holding.weight * 100).toFixed(0)}% · {money((Number.isFinite(amount) ? amount : 0) * holding.weight)}</span></div>)}<p className="sub">Version {parent.proposal?.version || 1}. You approve this plan only. No automatic changes. A small amount is reserved for estimated trading costs.</p></div>
            <div className="demo-test"><strong>{parent.test?.real ? 'Historical test' : 'Simulated example'}</strong><p>{parent.test?.real ? 'Based on available price history. Past results do not predict future returns.' : 'This shows how the product works. It is not evidence that this trade will make money.'}</p><div className="kv"><span>Test result</span><span>{Number(parent.test?.return_pct || 0).toFixed(2)}%</span></div></div>
            {copies.length < 2 ? <>
              <label className="demo-label">How much would {person === 'You' ? 'you' : 'your friend'} put in?<span className="demo-amount">$<input type="number" min="1" max="1000" step="1" value={Number.isFinite(amount) ? amount : ''} onChange={(event) => setAmount(event.target.value === '' ? NaN : Number(event.target.value))} aria-label="Practice trade amount" disabled={busy || !!mine?.pledge_usd} /></span></label>
              <p className="sub">This amount belongs to {person.toLowerCase()} only. It is not added to a shared pot.</p>
              {mine?.pledge_usd ? <div className="demo-confirmed"><p>{person}: {money(mine.pledge_usd)} confirmed.</p><button className="primary" onClick={() => setPerson(PEOPLE.find((name) => name !== person))}>Next: switch to {person === 'You' ? 'your friend' : 'you'}</button></div> : <button className="primary" disabled={busy || !demoMode || !ready} onClick={() => send(`in for ${amount}`)}>{busy ? 'Saving…' : `Confirm my ${money(amount)} practice trade`}</button>}
            </> : <div className="demo-confirmed"><h2>{completeCopies.length === 2 ? 'Two people. Two separate trades.' : 'Some practice orders did not fill.'}</h2><p>{completeCopies.length === 2 ? 'You both copied the same idea. Each practice account has its own positions and results.' : 'An account was created, but that does not mean every order filled. Filled orders remain visible; missing orders were not replaced with a different asset.'}</p><button onClick={() => { window.location.hash = '#/demo?room=' + crypto.randomUUID().replaceAll('-', '').slice(0, 24) }}>Start a new demo</button></div>}
          </>}
        {error && <p className="err" role="alert">{error}</p>}
      </div>
      <aside className="demo-results">{busy ? <div className="probe-status" role="status"><Probe state={!parent ? 'thinking' : 'working'} /><span>{!parent ? 'Testing your idea…' : 'Updating your practice account…'}</span></div> : completeCopies.length === 2 ? <Probe state="success" /> : <ProbeConversation label={parent ? 'Same idea. Each friend chooses their own amount.' : 'Start a conversation with an idea.'} />}<h2>Your trade copies</h2>{PEOPLE.map((name) => {
        const copy = copies.find((item) => item.author === name)
        const backer = parent?.backers.find((item) => item.who === name)
        const fills = copy?.triggers || []
        const complete = holdings.length > 0 && fills.length === holdings.length
        return <article className="card pad" key={name}><div className="kv"><h3>{name}</h3><span className="sub">{complete ? 'Practice trade filled' : fills.length ? 'Partly filled' : backer?.pledge_usd ? 'Ready' : 'Not confirmed'}</span></div><strong className="demo-balance">{money(copy?.pledged_usd || backer?.pledge_usd)}</strong><p className="sub">{fills.length ? 'Your separate practice account' : 'Choose an amount to try the trade'}</p>{fills.map((fill) => <div className="demo-fill" key={fill.market}><div className="kv"><span>Market</span><span>{fill.market}</span></div><div className="kv"><span>Trade value</span><span>{money(fill.size * fill.entry_px)}</span></div><div className="kv"><span>Amount bought</span><span>{Number(fill.size).toFixed(6)}</span></div><div className="kv"><span>Price</span><span>{money(fill.entry_px)}</span></div><span className="sub">Simulated fill. No real funds moved.</span></div>)}</article>
      })}<p className="sub">The Telegram demo follows the same steps with real Telegram identities. Real-money copies still need separate wallet authorization.</p></aside>
    </div>
  </section>
}
