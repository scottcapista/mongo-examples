import React, { useCallback, useEffect, useState } from 'react'
import RecordCard from './RecordCard'

const API_URL = import.meta.env.VITE_API_URL || ''
const FETCH_OPTS = { credentials: 'include' }

const COLLECTION_LABELS = {
  episodic: 'Episodic',
  semantic: 'Semantic',
  all: 'All',
}

export default function UserMemory({ username, authUser }) {
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [collection, setCollection] = useState('all')
  const [memoryType, setMemoryType] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadPage = useCallback(async (p, coll, typeFilter) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        page: String(p),
        limit: '10',
        collection: coll,
      })
      if (typeFilter) params.set('memory_type', typeFilter)

      const res = await fetch(`${API_URL}/admin/user-memory?${params}`, FETCH_OPTS)
      const json = await res.json()
      if (!res.ok) throw new Error(json.error || 'Failed to load memories')
      setData(json)
      setPage(p)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!authUser) {
      setLoading(false)
      return
    }
    loadPage(1, collection, memoryType)
  }, [authUser, collection, memoryType, loadPage])

  if (!authUser) {
    return (
      <div className="user-memory">
        <h2>User Memory</h2>
        <p className="dataset-list__empty">
          Sign in to view memories stored for your account.
        </p>
      </div>
    )
  }

  return (
    <div className="user-memory">
      <div className="dataset-list__toolbar">
        <div>
          <h2>User Memory</h2>
          <p className="user-memory__subtitle">
            Memories for <strong>{username}</strong>
          </p>
        </div>
      </div>

      <div className="user-memory__filters">
        <label className="user-memory__filter">
          <span>Collection</span>
          <select
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
            disabled={loading}
          >
            {Object.entries(COLLECTION_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className="user-memory__filter">
          <span>Memory type</span>
          <input
            type="text"
            value={memoryType}
            onChange={(e) => setMemoryType(e.target.value.trim())}
            placeholder="e.g. user_preference"
            disabled={loading}
          />
        </label>
      </div>

      {loading && !data && (
        <div className="admin-loading">Loading memories…</div>
      )}

      {error && !data && (
        <div className="admin-error"><p>{error}</p></div>
      )}

      {data && (
        <>
          <p className="dataset-detail__meta">
            {data.total ?? 0} memories
            {data.filters?.collection && data.filters.collection !== 'all' && (
              <> · {COLLECTION_LABELS[data.filters.collection] || data.filters.collection}</>
            )}
          </p>

          {loading && <p className="admin-loading-inline">Loading page…</p>}

          <div className="record-list">
            {(data.records || []).length === 0 && !loading ? (
              <p className="dataset-list__empty">No memories found for your account.</p>
            ) : (
              (data.records || []).map((record) => (
                <div key={`${record.collection}-${record.data?.id || record.row_index}`} className="memory-card-wrap">
                  <div className="memory-card__meta">
                    <span className={`memory-badge memory-badge--${record.collection}`}>
                      {record.collection}
                    </span>
                    {record.data?.memory_type && (
                      <span className="memory-badge memory-badge--type">
                        {record.data.memory_type}
                      </span>
                    )}
                    {record.data?.session_id && (
                      <span className="memory-card__session" title={record.data.session_id}>
                        session: {record.data.session_id.slice(0, 8)}…
                      </span>
                    )}
                  </div>
                  <RecordCard record={record} />
                </div>
              ))
            )}
          </div>

          {data.total_pages > 1 && (
            <div className="pagination">
              <button
                type="button"
                className="btn-secondary"
                disabled={page <= 1 || loading}
                onClick={() => loadPage(page - 1, collection, memoryType)}
              >
                Previous
              </button>
              <span className="pagination__label">
                Page {page} of {data.total_pages}
              </span>
              <button
                type="button"
                className="btn-secondary"
                disabled={page >= data.total_pages || loading}
                onClick={() => loadPage(page + 1, collection, memoryType)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
