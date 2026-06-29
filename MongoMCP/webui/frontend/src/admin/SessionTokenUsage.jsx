import React, { useCallback, useEffect, useState } from 'react'
import SessionTimelineChart from './SessionTimelineChart'

const API_URL = import.meta.env.VITE_API_URL || ''
const FETCH_OPTS = { credentials: 'include' }

function formatTokens(n) {
  return (n ?? 0).toLocaleString()
}

function formatTs(ts) {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return String(ts)
  }
}

function formatSessionLabel(s) {
  if (!s?.session_id) return '—'
  const short = s.session_id.length > 12 ? `${s.session_id.slice(0, 12)}…` : s.session_id
  const when = s.last_seen ? formatTs(s.last_seen) : ''
  return `${short} (${formatTokens(s.total_tokens)} tok, ${when})`
}

function StatusBadge({ status }) {
  const ok = status === 'success'
  return (
    <span className={`usage-badge usage-badge--${ok ? 'success' : 'error'}`}>
      {status || 'unknown'}
    </span>
  )
}

export default function SessionTokenUsage({ username, authUser }) {
  const [records, setRecords] = useState(null)
  const [summary, setSummary] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState('')
  const [page, setPage] = useState(1)
  const [bucket, setBucket] = useState('day')
  const [timelineBucket, setTimelineBucket] = useState('hour')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [historyDetail, setHistoryDetail] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(false)

  const email = authUser?.email || username

  const loadData = useCallback(async (p, bucketUnit, selectedSession, chartBucket) => {
    if (!email) return
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        page: String(p),
        limit: '20',
        username: email,
      })
      if (selectedSession) params.set('session_id', selectedSession)

      const summaryParams = new URLSearchParams({
        username: email,
        bucket: bucketUnit,
      })
      if (selectedSession) summaryParams.set('session_id', selectedSession)

      const timelineParams = new URLSearchParams({
        username: email,
        bucket: chartBucket,
      })
      if (selectedSession) timelineParams.set('session_id', selectedSession)

      const sessionsParams = new URLSearchParams({ limit: '30' })

      const [listRes, summaryRes, timelineRes, sessionsRes] = await Promise.all([
        fetch(`${API_URL}/admin/session-token-usage?${params}`, FETCH_OPTS),
        fetch(`${API_URL}/admin/session-token-usage/summary?${summaryParams}`, FETCH_OPTS),
        fetch(`${API_URL}/admin/session-timeline?${timelineParams}`, FETCH_OPTS),
        fetch(`${API_URL}/admin/session-token-usage/sessions?${sessionsParams}`, FETCH_OPTS),
      ])
      const listJson = await listRes.json()
      const summaryJson = await summaryRes.json()
      const timelineJson = await timelineRes.json()
      const sessionsJson = await sessionsRes.json()
      if (!listRes.ok) throw new Error(listJson.error || 'Failed to load usage records')
      if (!summaryRes.ok) throw new Error(summaryJson.error || 'Failed to load usage summary')
      if (!timelineRes.ok) throw new Error(timelineJson.error || 'Failed to load session timeline')
      if (!sessionsRes.ok) throw new Error(sessionsJson.error || 'Failed to load sessions')
      setRecords(listJson)
      setSummary(summaryJson)
      setTimeline(timelineJson)
      setSessions(sessionsJson.sessions || [])
      setPage(p)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [email])

  useEffect(() => {
    if (!authUser) {
      setLoading(false)
      return
    }
    loadData(1, bucket, sessionId, timelineBucket)
  }, [authUser, bucket, sessionId, timelineBucket, loadData])

  async function openHistory(llmHistoryId) {
    if (!llmHistoryId) return
    setHistoryLoading(true)
    setHistoryDetail(null)
    try {
      const res = await fetch(`${API_URL}/admin/llm-history/${llmHistoryId}`, FETCH_OPTS)
      const json = await res.json()
      if (!res.ok) throw new Error(json.error || 'Failed to load history')
      setHistoryDetail(json)
    } catch (e) {
      setHistoryDetail({ error: String(e) })
    } finally {
      setHistoryLoading(false)
    }
  }

  if (!authUser) {
    return (
      <div className="session-token-usage">
        <h2>Token Usage</h2>
        <p className="dataset-list__empty">Sign in to view LLM token usage for your account.</p>
      </div>
    )
  }

  return (
    <div className="session-token-usage">
      <div className="dataset-list__toolbar">
        <div>
          <h2>Token Usage</h2>
          <p className="user-memory__subtitle">
            Per-LLM-call metrics for <strong>{email}</strong>
          </p>
        </div>
      </div>

      <div className="user-memory__filters">
        <label className="user-memory__filter">
          <span>Session</span>
          <select
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            disabled={loading}
          >
            <option value="">All sessions</option>
            {sessions.map((s) => (
              <option key={s.session_id} value={s.session_id}>
                {formatSessionLabel(s)}
              </option>
            ))}
          </select>
        </label>
        <label className="user-memory__filter">
          <span>Summary bucket</span>
          <select value={bucket} onChange={(e) => setBucket(e.target.value)} disabled={loading}>
            <option value="hour">Hour</option>
            <option value="day">Day</option>
            <option value="month">Month</option>
          </select>
        </label>
        <label className="user-memory__filter">
          <span>Chart bucket</span>
          <select
            value={timelineBucket}
            onChange={(e) => setTimelineBucket(e.target.value)}
            disabled={loading}
          >
            <option value="hour">Hour</option>
            <option value="day">Day</option>
            <option value="month">Month</option>
          </select>
        </label>
      </div>

      {loading && !records && <div className="admin-loading">Loading token usage…</div>}
      {error && !records && <div className="admin-error"><p>{error}</p></div>}

      {(timeline?.points?.length > 0 || sessionId) && (
        <section className="usage-summary">
          <h3 className="usage-section-title">
            Session timeline
            {sessionId && (
              <span className="usage-section-meta">
                {' '}
                — {sessionId.slice(0, 16)}{sessionId.length > 16 ? '…' : ''}
              </span>
            )}
          </h3>
          <SessionTimelineChart points={timeline?.points} bucketUnit={timeline?.bucket_unit} />
        </section>
      )}

      {summary?.buckets?.length > 0 && (
        <section className="usage-summary">
          <h3 className="usage-section-title">Usage over time</h3>
          <div className="usage-table-wrap">
            <table className="usage-table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th>Model</th>
                  <th>Calls</th>
                  <th>Errors</th>
                  <th>In tokens</th>
                  <th>Out tokens</th>
                  <th>Cache read</th>
                  <th>Cache write</th>
                  <th>Total</th>
                  <th>Avg latency</th>
                </tr>
              </thead>
              <tbody>
                {summary.buckets.map((row, idx) => (
                  <tr key={`${row.bucket}-${row.model_id}-${idx}`}>
                    <td>{formatTs(row.bucket)}</td>
                    <td className="usage-table__mono">{row.model_id || '—'}</td>
                    <td>{row.call_count}</td>
                    <td>{row.error_count}</td>
                    <td>{formatTokens(row.input_tokens)}</td>
                    <td>{formatTokens(row.output_tokens)}</td>
                    <td>{formatTokens(row.cache_read_input_tokens)}</td>
                    <td>{formatTokens(row.cache_creation_input_tokens)}</td>
                    <td>{formatTokens(row.total_tokens)}</td>
                    <td>{row.avg_latency_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {records && (
        <section className="usage-calls">
          <h3 className="usage-section-title">
            LLM calls {records.total != null && <span className="usage-section-meta">({records.total} total)</span>}
          </h3>

          {loading && <p className="admin-loading-inline">Refreshing…</p>}

          {(records.records || []).length === 0 && !loading ? (
            <p className="dataset-list__empty">
              No usage records yet. Send a chat message to generate LLM call metrics.
            </p>
          ) : (
            <div className="usage-table-wrap">
              <table className="usage-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Session</th>
                    <th>Iter</th>
                    <th>Status</th>
                    <th>In</th>
                    <th>Out</th>
                    <th>Cache read</th>
                    <th>Cache write</th>
                    <th>Total</th>
                    <th>Latency</th>
                    <th>History</th>
                  </tr>
                </thead>
                <tbody>
                  {(records.records || []).map((row) => (
                    <tr key={row.id || `${row.timestamp}-${row.iteration}`}>
                      <td>{formatTs(row.timestamp)}</td>
                      <td className="usage-table__mono" title={row.meta?.session_id}>
                        {row.meta?.session_id
                          ? `${row.meta.session_id.slice(0, 8)}…`
                          : '—'}
                      </td>
                      <td>{row.iteration ?? '—'}</td>
                      <td>
                        <StatusBadge status={row.status} />
                        {row.error && (
                          <span className="usage-error-hint" title={row.error}>ⓘ</span>
                        )}
                      </td>
                      <td>{formatTokens(row.input_tokens)}</td>
                      <td>{formatTokens(row.output_tokens)}</td>
                      <td>{formatTokens(row.cache_read_input_tokens)}</td>
                      <td>{formatTokens(row.cache_creation_input_tokens)}</td>
                      <td>{formatTokens(row.total_tokens)}</td>
                      <td>{row.latency_ms != null ? `${Math.round(row.latency_ms)} ms` : '—'}</td>
                      <td>
                        {row.llm_history_id ? (
                          <button
                            type="button"
                            className="btn-link"
                            onClick={() => openHistory(row.llm_history_id)}
                          >
                            {row.llm_history_id.slice(0, 8)}…
                          </button>
                        ) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {records.total_pages > 1 && (
            <div className="pagination">
              <button
                type="button"
                className="btn-secondary"
                disabled={page <= 1 || loading}
                onClick={() => loadData(page - 1, bucket, sessionId, timelineBucket)}
              >
                Previous
              </button>
              <span className="pagination__label">Page {page} of {records.total_pages}</span>
              <button
                type="button"
                className="btn-secondary"
                disabled={page >= records.total_pages || loading}
                onClick={() => loadData(page + 1, bucket, sessionId, timelineBucket)}
              >
                Next
              </button>
            </div>
          )}
        </section>
      )}

      {(historyDetail || historyLoading) && (
        <div className="usage-modal-backdrop" onClick={() => setHistoryDetail(null)}>
          <div className="usage-modal" onClick={(e) => e.stopPropagation()}>
            <div className="usage-modal__header">
              <h3>LLM history</h3>
              <button type="button" className="btn-secondary" onClick={() => setHistoryDetail(null)}>Close</button>
            </div>
            {historyLoading && <p className="admin-loading-inline">Loading…</p>}
            {historyDetail?.error && <p className="admin-error">{historyDetail.error}</p>}
            {historyDetail && !historyDetail.error && (
              <pre className="usage-modal__body">{JSON.stringify(historyDetail, null, 2)}</pre>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
