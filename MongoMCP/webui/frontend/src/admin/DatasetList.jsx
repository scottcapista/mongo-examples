import React, { useEffect, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || ''

const CATEGORY_LABELS = {
  growth: 'Growth',
  config: 'Config',
  personalization: 'Personalization',
}

export default function DatasetList({ onSelect, onNew }) {
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`${API_URL}/admin/datasets`)
        const data = await res.json()
        if (!res.ok) throw new Error(data.error || 'Failed to load datasets')
        if (!cancelled) {
          const items = (data.datasets || []).map((ds) => ({
            ...ds,
            index_summary: ds.index_summary || (ds.indexes ? {
              database: ds.indexes.database_index_count || 0,
              search: ds.indexes.search_index_count || 0,
              vector: ds.indexes.vector_index_count || 0,
            } : null),
          }))
          setDatasets(items)
        }
      } catch (e) {
        if (!cancelled) setError(String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return <div className="admin-loading">Loading datasets…</div>
  }

  if (error) {
    return <div className="admin-error"><p>{error}</p></div>
  }

  return (
    <div className="dataset-list">
      <div className="dataset-list__toolbar">
        <h2>Datasets</h2>
        <button type="button" className="btn-send" onClick={onNew}>
          + New dataset
        </button>
      </div>

      {datasets.length === 0 ? (
        <p className="dataset-list__empty">No datasets yet. Upload your first one.</p>
      ) : (
        <div className="dataset-grid">
          {datasets.map((ds) => (
            <button
              key={ds.id}
              type="button"
              className={`dataset-card dataset-card--${ds.category || 'growth'}`}
              onClick={() => onSelect(ds.id)}
            >
              <span className="dataset-card__category">
                {CATEGORY_LABELS[ds.category] || ds.category}
              </span>
              <h3 className="dataset-card__name">{ds.name}</h3>
              <p className="dataset-card__description">
                {ds.description || 'No description'}
              </p>
              <span className="dataset-card__meta">
                {ds.source_type === 'cluster' ? 'Cluster' : 'Upload'} · {ds.record_count ?? 0} records · {ds.owner}
                {ds.index_summary && (
                  <> · idx {ds.index_summary.database}/{ds.index_summary.search}/{ds.index_summary.vector}</>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
