/** Format estimated USD cost for admin token usage UI. */
export function formatCost(usd) {
  if (usd == null || Number.isNaN(usd)) return '—'
  const n = Number(usd)
  if (n < 0.01) return `$${n.toFixed(4)}`
  if (n < 1) return `$${n.toFixed(3)}`
  return `$${n.toFixed(2)}`
}

export function costFromUsage(usage, modelId) {
  if (!usage || !modelId) return null
  const inTok = Number(usage.inputTokens ?? usage.input_tokens ?? 0)
  const outTok = Number(usage.outputTokens ?? usage.output_tokens ?? 0)
  const cacheRead = Number(usage.cacheReadInputTokens ?? usage.cache_read_input_tokens ?? 0)
  const cacheWrite = Number(usage.cacheCreationInputTokens ?? usage.cache_creation_input_tokens ?? 0)
  if (!inTok && !outTok && !cacheRead && !cacheWrite) return null
  // Client-side fallback only; APIs should supply estimated_cost_usd when available.
  const rates = {
    'claude-sonnet-4-6': { in: 3, out: 15, cr: 0.3, cw: 3.75 },
  }
  const key = String(modelId).replace(/^global\.anthropic\./, '')
  const r = rates[key]
  if (!r) return null
  return (
    inTok * r.in + outTok * r.out + cacheRead * r.cr + cacheWrite * r.cw
  ) / 1_000_000
}
