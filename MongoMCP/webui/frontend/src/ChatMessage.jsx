import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ExpandableTile from './ExpandableTile'
import JsonDataRenderer from './JsonDataRenderer'
import JsonViewer from './JsonViewer'

/**
 * Renders one conversation turn: user bubble + AI bubble + detail tiles.
 */

/** Extract a friendly display name from a model ID like "claude-sonnet-4-6" */
function friendlyModelName(modelId) {
  if (!modelId) return 'Atlas AI'
  // Strip cross-region prefix (e.g. "global.", "us.")
  const base = modelId.replace(/^[a-z-]+\./, '').replace(/^[a-z-]+\./, '')
  // Extract just the model slug after provider prefix
  const parts = base.split('.')
  const slug = parts[parts.length - 1] || parts[0]
  // Capitalise and clean up hyphens
  return slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export default function ChatMessage({
  userText,
  assistantText,
  toolCalls = [],
  reasoningSteps = [],
  mapData = null,
  isStreaming = false,
  modelId = '',
}) {
  const hasTools = toolCalls.length > 0
  const hasReasoning = reasoningSteps.length > 0
  const hasMap = !!mapData

  return (
    <div style={{ marginBottom: 24 }}>
      {/* User bubble — omitted for greeting turn */}
      {userText && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
          <div style={{
            maxWidth: '75%',
            background: '#00ED64',
            color: '#001E2B',
            borderRadius: '18px 18px 4px 18px',
            padding: '10px 16px',
            fontSize: 14,
            fontWeight: 500,
            lineHeight: 1.5,
            boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            {userText}
          </div>
        </div>
      )}

      {/* AI bubble */}
      {(assistantText || isStreaming) && (
        <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
          <div style={{ maxWidth: '85%' }}>
            {/* Avatar + name */}
            <div style={{ fontSize: 11, color: '#888', marginBottom: 4, marginLeft: 2 }}>
              <span style={{ fontWeight: 600, color: '#00684A' }}>● {friendlyModelName(modelId)}</span>
            </div>

            <div style={{
              background: '#fff',
              border: '1px solid #e8f5ee',
              borderRadius: '4px 18px 18px 18px',
              padding: '12px 16px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
            }}>
              {assistantText ? (
                <div className="markdown-content" style={{ fontSize: 14, lineHeight: 1.6 }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{assistantText}</ReactMarkdown>
                </div>
              ) : (
                <div style={{ color: '#aaa', fontSize: 13 }}>⏳ Thinking...</div>
              )}
            </div>

            {/* Map data */}
            {hasMap && (
              <div style={{ marginTop: 8 }}>
                <JsonDataRenderer jsonData={mapData} />
              </div>
            )}

            {/* Tile chips row */}
            {!isStreaming && (hasTools || hasReasoning || hasMap) && (
              <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>

                {hasTools && (
                  <ExpandableTile icon="🔧" label="Tools called" count={toolCalls.length}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      {toolCalls.map((tc, i) => (
                        <div key={i}>
                          <div style={{ fontWeight: 600, color: '#001E2B', marginBottom: 4 }}>
                            {i + 1}. <code style={{ background: '#e8f5ee', padding: '1px 6px', borderRadius: 4 }}>{tc.name}</code>
                          </div>
                          <div style={{ fontSize: 12, color: '#555', marginBottom: 4 }}>Input:</div>
                          <JsonViewer data={tc.input} />
                        </div>
                      ))}
                    </div>
                  </ExpandableTile>
                )}

                {hasTools && (
                  <ExpandableTile icon="📦" label="Tool responses" count={toolCalls.filter(tc => tc.result !== undefined).length}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      {toolCalls.map((tc, i) => (
                        <div key={i}>
                          <div style={{ fontWeight: 600, color: '#001E2B', marginBottom: 4 }}>
                            <code style={{ background: '#e8f5ee', padding: '1px 6px', borderRadius: 4 }}>{tc.name}</code>
                          </div>
                          {tc.result !== undefined ? (
                            <JsonViewer data={tc.result} />
                          ) : (
                            <span style={{ color: '#aaa', fontSize: 12 }}>No response captured</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </ExpandableTile>
                )}

                {hasReasoning && (
                  <ExpandableTile icon="🧠" label="Processing log" count={reasoningSteps.length}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      {reasoningSteps.map((step, i) => {
                        const rawMsg = typeof step === 'string' ? step : step.message
                        const sts = typeof step === 'string' ? '' : step.status
                        const msg = sts === 'LLM Reasoning' && rawMsg && rawMsg.length > 100
                          ? rawMsg.slice(0, 100) + '…'
                          : rawMsg
                        return (
                          <div key={i} style={{
                            fontSize: 12,
                            padding: '3px 0',
                            borderBottom: i < reasoningSteps.length - 1 ? '1px solid #eee' : 'none',
                            display: 'flex',
                            gap: 8,
                            alignItems: 'flex-start',
                          }}>
                            {sts && (
                              <span style={{
                                flexShrink: 0,
                                fontSize: 10,
                                fontWeight: 700,
                                color: '#fff',
                                background: sts === 'LLM Reasoning' ? '#00684A' : sts.includes('Error') ? '#c0392b' : '#334',
                                borderRadius: 8,
                                padding: '1px 6px',
                                marginTop: 1,
                              }}>
                                {sts}
                              </span>
                            )}
                            <span style={{ color: '#333', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{msg}</span>
                          </div>
                        )
                      })}
                    </div>
                  </ExpandableTile>
                )}

              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
