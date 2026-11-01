import React from 'react'
import { IDEAS, TELEGRAM_BOT, labLink } from './ideas.js'

export default function Homepage() {
  return <div className="product-home">
    <section className="product-hero">
      <div><p className="sub">Ideas from the group chat, traded for real.</p><h1>Your friends.<br />Your own trade.</h1>
      <p className="product-description">Say an idea in your Telegram group. Protoss tests it on real Hyperliquid history, then each friend picks an amount and the order goes out from their own account.</p>
      <div className="welcome-actions"><a className="btn primary" href={TELEGRAM_BOT} target="_blank" rel="noreferrer">Open Telegram</a><a className="btn" href="/app/#/lab">Test an idea</a></div></div>
      <img className="product-probe" src="/probe/idle.svg" alt="Probe, the Protoss research companion" />
    </section>
    <section aria-labelledby="ideas-h">
      <h2 id="ideas-h" className="ideas-h">Four ideas to start with</h2>
      <div className="ideas">
        {IDEAS.map((idea, i) => <article className="card idea" key={idea.market}>
          <span className="sub">{i + 1}</span>
          <h3>“{idea.said}”</h3>
          <p>{idea.trade}</p>
          <div className="idea-actions"><a className="btn sm" href={labLink(idea.said)}>Test it</a><a className="text-link" href={TELEGRAM_BOT} target="_blank" rel="noreferrer">Trade it in Telegram</a></div>
        </article>)}
      </div>
    </section>
    <section className="card product-next"><div><h2>Real accounts, real fills</h2><p>Every position is a real Hyperliquid position in the account that approved it. Balances, positions and fills come straight from the exchange.</p></div><a className="btn primary" href="/app/#/accounts">See the accounts</a></section>
    <p className="sub">Separate accounts, not pooled custody. xyz:ANT and xyz:UNITREE are perpetual markets, not shares of Anthropic or Unitree. A past result is not a promise of returns.</p>
  </div>
}
