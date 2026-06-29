import React, { useMemo } from 'react'
import { formatCost } from './formatCost'

const SERIES = [
  { key: 'total_tokens', label: 'Total tokens', color: '#3b82f6', axis: 'tokens' },
  { key: 'cache_read_input_tokens', label: 'Cache read', color: '#10b981', axis: 'tokens' },
  { key: 'cache_creation_input_tokens', label: 'Cache write', color: '#8b5cf6', axis: 'tokens' },
  { key: 'estimated_cost_usd', label: 'Est. cost ($)', color: '#eab308', axis: 'cost' },
  { key: 'strategy_store', label: 'Strategy save', color: '#f59e0b', axis: 'events' },
  { key: 'strategy_recall', label: 'Strategy use', color: '#ef4444', axis: 'events' },
  { key: 'tool_cache_hit', label: 'Tool cache hit', color: '#06b6d4', axis: 'events' },
]

function formatBucketLabel(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return String(ts)
  }
}

export default function SessionTimelineChart({ points, bucketUnit }) {
  const chart = useMemo(() => {
    const data = (points || []).slice().sort((a, b) => String(a.bucket).localeCompare(String(b.bucket)))
    if (!data.length) return null

    const width = 760
    const height = 280
    const pad = { top: 16, right: 88, bottom: 56, left: 56, costRight: 40 }
    const innerW = width - pad.left - pad.right
    const innerH = height - pad.top - pad.bottom

    const tokenMax = Math.max(
      1,
      ...data.flatMap((p) => [
        p.total_tokens || 0,
        p.cache_read_input_tokens || 0,
        p.cache_creation_input_tokens || 0,
      ]),
    )
    const eventMax = Math.max(
      1,
      ...data.flatMap((p) => [
        p.strategy_store || 0,
        p.strategy_recall || 0,
        p.tool_cache_hit || 0,
      ]),
    )
    const costMax = Math.max(
      0.0001,
      ...data.map((p) => p.estimated_cost_usd || 0),
    )

    const xAt = (i) => pad.left + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW)
    const yToken = (v) => pad.top + innerH - (v / tokenMax) * innerH
    const yEvent = (v) => pad.top + innerH - (v / eventMax) * innerH
    const yCost = (v) => pad.top + innerH - (v / costMax) * innerH

    const lines = SERIES.filter((s) => s.axis === 'tokens' || s.axis === 'cost').map((s) => ({
      ...s,
      yFn: s.axis === 'cost' ? yCost : yToken,
      path: data
        .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xAt(i)} ${(s.axis === 'cost' ? yCost : yToken)(p[s.key] || 0)}`)
        .join(' '),
      dashed: s.axis === 'cost',
    }))

    const eventBars = data.map((p, i) => {
      const groupW = Math.min(28, innerW / Math.max(data.length, 1) * 0.7)
      const cx = xAt(i)
      const events = SERIES.filter((s) => s.axis === 'events')
      const barW = groupW / events.length
      return events.map((s, j) => {
        const val = p[s.key] || 0
        const x = cx - groupW / 2 + j * barW
        const h = (val / eventMax) * innerH
        return {
          key: `${i}-${s.key}`,
          x,
          y: pad.top + innerH - h,
          w: Math.max(2, barW - 1),
          h,
          color: s.color,
          val,
        }
      })
    }).flat()

    const xLabels = data.map((p, i) => ({
      x: xAt(i),
      label: formatBucketLabel(p.bucket),
    }))

    return { width, height, pad, innerH, tokenMax, eventMax, costMax, lines, eventBars, xLabels, formatCost }
  }, [points])

  if (!chart) {
    return (
      <p className="dataset-list__empty session-timeline__empty">
        No timeline data yet. Chat activity in this session will appear here.
      </p>
    )
  }

  return (
    <div className="session-timeline">
      <div className="session-timeline__legend">
        {SERIES.map((s) => (
          <span key={s.key} className="session-timeline__legend-item">
            <span className="session-timeline__swatch" style={{ background: s.color }} />
            {s.label}
            {s.axis === 'events' ? ' (count)' : ''}
            {s.axis === 'cost' ? ' (USD)' : ''}
          </span>
        ))}
        {bucketUnit && (
          <span className="session-timeline__bucket-hint">Bucket: {bucketUnit}</span>
        )}
      </div>
      <svg
        className="session-timeline__svg"
        viewBox={`0 0 ${chart.width} ${chart.height}`}
        role="img"
        aria-label="Session metrics over time"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = chart.pad.top + chart.innerH * (1 - t)
          return (
            <g key={t}>
              <line
                x1={chart.pad.left}
                y1={y}
                x2={chart.width - chart.pad.right}
                y2={y}
                className="session-timeline__grid"
              />
              <text x={chart.pad.left - 8} y={y + 4} textAnchor="end" className="session-timeline__axis-label">
                {Math.round(chart.tokenMax * t).toLocaleString()}
              </text>
              <text
                x={chart.width - chart.pad.right + 8}
                y={y + 4}
                textAnchor="start"
                className="session-timeline__axis-label session-timeline__axis-label--right"
              >
                {Math.round(chart.eventMax * t)}
              </text>
              <text
                x={chart.width - 8}
                y={y + 4}
                textAnchor="end"
                className="session-timeline__axis-label session-timeline__axis-label--cost"
              >
                {formatCost(chart.costMax * t)}
              </text>
            </g>
          )
        })}

        {chart.eventBars.map((b) => (
          <rect
            key={b.key}
            x={b.x}
            y={b.y}
            width={b.w}
            height={b.h}
            fill={b.color}
            opacity={0.55}
            rx={1}
          />
        ))}

        {chart.lines.map((line) => (
          <path
            key={line.key}
            d={line.path}
            fill="none"
            stroke={line.color}
            strokeWidth={line.dashed ? 2 : 2}
            strokeDasharray={line.dashed ? '6 4' : undefined}
            strokeLinejoin="round"
          />
        ))}

        {chart.xLabels.map((lbl, i) => (
          <text
            key={lbl.label + i}
            x={lbl.x}
            y={chart.height - 12}
            textAnchor="middle"
            className="session-timeline__axis-label session-timeline__axis-label--x"
          >
            {lbl.label}
          </text>
        ))}

        <text x={12} y={chart.pad.top + 8} className="session-timeline__axis-title">Tokens</text>
        <text x={chart.width - chart.pad.right + 8} y={chart.pad.top + 8} className="session-timeline__axis-title">Events</text>
        <text x={chart.width - 8} y={chart.pad.top + 8} textAnchor="end" className="session-timeline__axis-title session-timeline__axis-title--cost">USD</text>
      </svg>
    </div>
  )
}
