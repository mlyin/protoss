import React, { useId } from 'react'
import probe from '../../brand/probe.svg?raw'

const labels = { idle: 'Protoss Probe hovering', thinking: 'Protoss Probe thinking', talking: 'Protoss Probe talking', working: 'Protoss Probe working', success: 'Protoss Probe, result ready' }

export default function Probe({ state = 'idle', size = 96, className = '' }) {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const selected = Object.hasOwn(labels, state) ? state : 'idle'
  // Static, repository-owned SVG only. Prefix IDs so multiple mascots never share gradients.
  const svg = probe.replace('class="probe idle"', `class="probe ${selected}"`)
    .replace(/id="([^"]+)"/g, (_, name) => `id="${id}-${name}"`)
    .replace(/url\(#([^)]+)\)/g, (_, name) => `url(#${id}-${name})`)
    .replace('aria-labelledby="title"', `aria-labelledby="${id}-title"`)
    .replace('Protoss Probe, hovering', labels[selected])
  return <div className={`probe-mascot ${className}`} style={{ width: size, maxWidth: '100%' }}
    dangerouslySetInnerHTML={{ __html: svg }} />
}

export function ProbeConversation({ label = 'Share an idea. Make it your own.', size = 110 }) {
  return <div className="probe-conversation"><div className="probe-pair" aria-label="Two Probes sharing an idea">
    <Probe state="talking" size={size} /><span className="probe-signal" aria-hidden="true"><i /><i /><i /></span>
    <Probe state="talking" size={size} className="probe-friend" /></div><p className="sub">{label}</p></div>
}

export function ProbeGallery() {
  const states = [ ['idle', 'Ready when you are', 'A quiet hover while you choose an idea.'],
    ['thinking', 'Thinking it through', 'Shown while your backtest is running.'],
    ['talking', 'Sharing an idea', 'Two friends discuss the same idea.'],
    ['working', 'Checking the trade', 'Waiting for wallet or exchange confirmation.'],
    ['success', 'Result ready', 'The result has arrived. This does not mean a profitable trade.'] ]
  return <section className="probe-gallery"><span className="sub">Meet the Protoss Probe</span><h1>A little character.<br />At every step.</h1>
    <p className="sub">Animated SVGs connected to the app’s actual state. Reduced-motion settings are respected.</p>
    <div className="probe-state-grid">{states.map(([state, title, detail]) => <article className="card pad" key={state}>
      <Probe state={state} size={200} /><h2>{title}</h2><p className="sub">{detail}</p>
      <a className="btn ghost" href={`/probe/${state}.svg`} download>Download SVG</a></article>)}</div>
    <div className="card pad probe-duet"><ProbeConversation size={180} label="One idea. Two independent decisions." />
      <a className="btn ghost" href="/probe/conversation.svg" download>Download two-Probe SVG</a></div>
  </section>
}
