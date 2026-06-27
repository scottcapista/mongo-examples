import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const API_URL = import.meta.env.VITE_API_URL || ''

export default function RecordCard({ record, datasetId, username, owner, onSaved }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(record.markdown || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const isOwner = username && owner && username === owner

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`${API_URL}/admin/datasets/${datasetId}/records/${record.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, display_markdown: draft }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || 'Failed to save')
      setEditing(false)
      onSaved?.(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  function handleEdit() {
    setDraft(record.markdown || '')
    setEditing(true)
    setError(null)
  }

  return (
    <div className="record-card">
      <div className="record-card__header">
        <span className="record-card__index">#{record.row_index + 1}</span>
        {isOwner && !editing && (
          <button type="button" className="btn-secondary" onClick={handleEdit}>
            Edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="record-card__edit">
          <textarea
            className="record-card__textarea"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={8}
          />
          <div className="record-card__actions">
            <button type="button" className="btn-send" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setEditing(false)}
              disabled={saving}
            >
              Cancel
            </button>
          </div>
          {error && <p className="record-card__error">{error}</p>}
        </div>
      ) : (
        <div className="record-card__markdown markdown-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{record.markdown || '_Empty_'}</ReactMarkdown>
        </div>
      )}
    </div>
  )
}
