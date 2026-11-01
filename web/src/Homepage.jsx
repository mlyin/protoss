import React from 'react'
import IdeaChat from './IdeaChat.jsx'
export default function Homepage() {
  return <div className="product-home">
    <section className="product-hero"><p className="sub">An idea worth sharing.</p><h1>Your friends.<br />Your own trade.</h1>
      <p className="product-description">A hack. A robotics thesis. An AI bubble. A podcast. Start with what you believe, find the market, and decide together.</p>
    </section>
    <IdeaChat />
    <div className="product-links"><a href="/app/">Your friends &amp; positions ↗</a><a href="https://t.me/ProtossTradingDemoBot" target="_blank" rel="noreferrer">Open Telegram ↗</a></div>
  </div>
}
