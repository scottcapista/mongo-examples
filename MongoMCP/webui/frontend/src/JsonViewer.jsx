import React, { useState } from 'react'

const MAX_STRING_LEN = 160
const ARRAY_PREVIEW = 8

function deepParse(val) {
  if (typeof val !== 'string') return val
  let v = val
  for (let i = 0; i < 3; i++) {
    try {
      const parsed = JSON.parse(v)
      if (typeof parsed === 'string') {
        v = parsed
        continue
      }
      return parsed
    } catch {
      break
    }
  }
  return v
}

function highlight(str) {
  return str.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      if (/^"/.test(match)) {
        if (/:$/.test(match)) return `<span class="json-raw__key">${match}</span>`
        return `<span class="json-raw__string">${match}</span>`
      }
      if (/true|false/.test(match)) return `<span class="json-raw__bool">${match}</span>`
      if (/null/.test(match)) return `<span class="json-raw__null">${match}</span>`
      return `<span class="json-raw__number">${match}</span>`
    }
  )
}

function JsonString({ value }) {
  const [expanded, setExpanded] = useState(false)
  if (value.length <= MAX_STRING_LEN || expanded) {
    return (
      <span className="json-tree__string">
        "{value}"
        {value.length > MAX_STRING_LEN && (
          <button type="button" className="json-tree__toggle" onClick={() => setExpanded(false)}>
            less
          </button>
        )}
      </span>
    )
  }
  return (
    <span className="json-tree__string">
      "{value.slice(0, MAX_STRING_LEN)}…"
      <button type="button" className="json-tree__toggle" onClick={() => setExpanded(true)}>
        more
      </button>
    </span>
  )
}

function JsonNode({ data, depth = 0 }) {
  const [open, setOpen] = useState(depth < 2)
  const [showAllItems, setShowAllItems] = useState(false)

  if (data === null) return <span className="json-tree__null">null</span>
  if (typeof data === 'boolean') return <span className="json-tree__bool">{String(data)}</span>
  if (typeof data === 'number') return <span className="json-tree__number">{data}</span>
  if (typeof data === 'string') return <JsonString value={data} />

  const isArray = Array.isArray(data)
  const entries = isArray ? data.map((v, i) => [i, v]) : Object.entries(data)
  const isEmpty = entries.length === 0
  const bracket = isArray ? ['[', ']'] : ['{', '}']

  if (isEmpty) {
    return <span className="json-tree__bracket">{bracket[0]}{bracket[1]}</span>
  }

  const hasHiddenItems = isArray && entries.length > ARRAY_PREVIEW && !showAllItems
  const visibleEntries = hasHiddenItems ? entries.slice(0, ARRAY_PREVIEW) : entries
  const hiddenCount = entries.length - ARRAY_PREVIEW

  return (
    <span className="json-tree__node">
      <button type="button" className="json-tree__branch" onClick={() => setOpen((o) => !o)}>
        {open ? '▾' : '▸'} {bracket[0]}
      </button>
      {!open && (
        <button type="button" className="json-tree__meta" onClick={() => setOpen(true)}>
          {isArray ? ` ${entries.length} items ` : ` ${entries.length} keys `}{bracket[1]}
        </button>
      )}
      {open && (
        <div className="json-tree__children">
          {visibleEntries.map(([key, value], index) => (
            <div key={String(key)} className="json-tree__row">
              {!isArray && <span className="json-tree__key">"{key}"</span>}
              {!isArray && <span className="json-tree__colon">: </span>}
              <JsonNode data={value} depth={depth + 1} />
              {index < visibleEntries.length - 1 && <span className="json-tree__comma">,</span>}
            </div>
          ))}
          {hasHiddenItems && (
            <button
              type="button"
              className="json-tree__more"
              onClick={() => setShowAllItems(true)}
            >
              … {hiddenCount} more items
            </button>
          )}
          {showAllItems && isArray && entries.length > ARRAY_PREVIEW && (
            <button
              type="button"
              className="json-tree__more"
              onClick={() => setShowAllItems(false)}
            >
              show fewer items
            </button>
          )}
        </div>
      )}
      {open && <span className="json-tree__bracket">{bracket[1]}</span>}
    </span>
  )
}

function PrettyJson({ data, maxHeight }) {
  const parsed = deepParse(data)
  const text = typeof parsed === 'string' ? parsed : JSON.stringify(parsed, null, 2)
  const html = highlight(text)
  return (
    <pre
      className="json-raw"
      style={{ maxHeight }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

export default function JsonViewer({ data, variant = 'dark', maxHeight = 420 }) {
  const [mode, setMode] = useState('tree')
  const parsed = deepParse(data)

  if (data === null || data === undefined) {
    return <p className="json-viewer__empty">No data</p>
  }

  const isObj = parsed !== null && typeof parsed === 'object'

  return (
    <div className={`json-viewer json-viewer--${variant}`}>
      {isObj && (
        <div className="json-viewer__toolbar">
          {['tree', 'raw'].map((m) => (
            <button
              key={m}
              type="button"
              className={`json-viewer__mode${mode === m ? ' json-viewer__mode--active' : ''}`}
              onClick={() => setMode(m)}
            >
              {m}
            </button>
          ))}
        </div>
      )}
      {mode === 'tree' && isObj ? (
        <div className="json-tree" style={{ maxHeight }}>
          <JsonNode data={parsed} depth={0} />
        </div>
      ) : (
        <PrettyJson data={data} maxHeight={maxHeight} />
      )}
    </div>
  )
}
