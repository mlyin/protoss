import React from 'react'
import IdeaChat from './IdeaChat.jsx'
export default function Homepage() {
  return <div className="product-home">
    <section className="product-hero"><h1>Predict anything.<br />Test anything.<br />Trade anything.<br />With your friends.</h1>
      <p className="product-description">Share an idea. Check the evidence. Find a market on Hyperliquid. Each person decides whether to trade.</p>
    </section>
    <IdeaChat />
    <div className="product-links"><a href="/app/">Your friends &amp; positions ↗</a><a href="https://t.me/ProtossTradingDemoBot" target="_blank" rel="noreferrer">Open Telegram ↗</a></div>
  </div>
}
