import React, { useCallback, useEffect, useState } from 'react'
import RecordCard from './RecordCard'

const API_URL = import.meta.env.VITE_API_URL || ''

const CATEGORY_LABELS = {
  growth: 'Growth',
  config: 'Config',
  personalization: 'Personalization',
}

export default function DatasetDetail({ datasetId, username, onBack }) {
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadPage = useCallback(async (p) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(
        `${API_URL}/admin/datasets/${datasetId}/records?page=${p}&limit=10`
      )
      const json = await res.json()
      if (!res.ok) throw new Error(json.error || 'Failed to load records')
      setData(json)
      setPage(p)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [datasetId])

  useEffect(() => {
    loadPage(1)
  }, [loadPage])

  function handleRecordSaved(updated) {
    setData((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        records: prev.records.map((r) => (r.id === updated.id ? { ...r, ...updated, markdown: updated.markdown } : r)),
      }
    })
  }

  if (loading && !data) {
    return <div className="admin-loading">Loading dataset…</div>
  }

  if (error && !data) {
    return (
      <div className="admin-error">
        <p>{error}</p>
        <button type="button" className="btn-secondary" onClick={onBack}>Back</button>
      </div>
    )
  }

  const ds = data?.dataset
  const category = ds?.category || 'growth'

  return (
    <div className="dataset-detail">
      <button type="button" className="btn-secondary admin-back-btn" onClick={onBack}>
        ← Back to datasets
      </button>

      <header className="dataset-detail__header">
        <h2>{ds?.name}</h2>
        <span className={`dataset-badge dataset-badge--${category}`}>
          {CATEGORY_LABELS[category] || category}
        </span>
      </header>
      {ds?.description && <p className="dataset-detail__description">{ds.description}</p>}
      <p className="dataset-detail__meta">
        Owner: <strong>{ds?.owner}</strong> · {data?.total ?? 0} records
      </p>

      {loading && <p className="admin-loading-inline">Loading page…</p>}

      <div className="record-list">
        {(data?.records || []).map((record) => (
          <RecordCard
            key={record.id}
            record={record}
            datasetId={datasetId}
            username={username}
            owner={ds?.owner}
            onSaved={handleRecordSaved}
          />
        ))}
      </div>

      {data && data.total_pages > 1 && (
        <div className="pagination">
          <button
            type="button"
            className="btn-secondary"
            disabled={page <= 1 || loading}
            onClick={() => loadPage(page - 1)}
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
            onClick={() => loadPage(page + 1)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
