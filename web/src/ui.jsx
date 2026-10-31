import React from 'react'

// Small shared pieces: skeletons (the shape of the data before the data) and the status mark.

export function SkelLines({ n = 4, widths = ['60%', '90%', '75%', '40%'] }) {
  return <div className="skel-lines" aria-hidden="true">{Array.from({ length: n }, (_, i) => <span className="skel" key={i} style={{ width: widths[i % widths.length] }} />)}</div>
}

export function SkelRows({ n = 4 }) {
  return (
    <div className="skel-rows" aria-hidden="true">
      {Array.from({ length: n }, (_, i) => (
        <div className="r" key={i}><span className="skel" /><span className="skel" style={{ width: `${55 + (i * 17) % 40}%` }} /><span className="skel" /><span className="skel" /><span className="skel" style={{ width: '60%' }} /></div>
      ))}
    </div>
  )
}

export function St({ live }) {
  return <span className={`st ${live ? 'live' : 'halted'}`}>{live ? 'live' : 'halted'}</span>
}
