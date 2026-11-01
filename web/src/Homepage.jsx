import React from 'react'
export default function Homepage() {
  return <div className="product-home">
    <section className="product-hero">
      <div><p className="sub">An idea worth sharing.</p><h1>Your friends.<br />Your own trade.</h1>
      <p className="product-description">Share a trading idea in your group. Test it against history. Everyone chooses their own amount, approves from their own wallet, and keeps their own position.</p>
      <div className="welcome-actions"><a className="btn primary" href="/app/">Try the practice app</a><a className="btn" href="/app/#/lab">Test an idea</a></div>
      <p className="sub">Practice uses the same app with simulated balances and fills. No deposit or wallet signature needed.</p></div>
      <img className="product-probe" src="/probe/idle.svg" alt="Probe, the Protoss research companion" />
    </section>
    <section className="product-steps" aria-label="How it works">
      {[['1', 'Bring an idea', 'A market, a reason, and something that would prove you wrong.'], ['2', 'Look before you trade', 'Use the research page to test assumptions and inspect the results.'], ['3', 'Choose your own amount', 'Friends can follow the same thesis while keeping separate wallets and exits.'], ['4', 'Approve and follow', 'Real trades need individual approval. Practice fills are clearly labeled.']].map(([n, title, copy]) => <article className="card" key={n}><span className="sub">{n}</span><h2>{title}</h2><p>{copy}</p></article>)}
    </section>
    <section className="card product-next"><div><h2>Start with a practice group</h2><p>Explore the group conversation, research, balances, and fills in the app.</p></div><a className="btn primary" href="/app/#/huddle/demo">Open group chat</a><a className="text-link" href="https://t.me/ProtossTradingDemoBot">Open Telegram</a></section>
    <p className="sub">Separate accounts, not pooled custody. ANT is a perpetual market, not ownership of Anthropic shares. Practice results are not a promise of returns.</p>
  </div>
}
