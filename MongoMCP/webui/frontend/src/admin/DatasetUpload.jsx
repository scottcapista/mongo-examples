import React, { useRef, useState } from 'react'
import ProgressBar from './ProgressBar'

const API_URL = import.meta.env.VITE_API_URL || ''

const CATEGORIES = [
  { value: 'growth', label: 'Growth' },
  { value: 'config', label: 'Config' },
  { value: 'personalization', label: 'Personalization' },
]

export default function DatasetUpload({ username, onComplete, onCancel }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('growth')
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [showProgress, setShowProgress] = useState(false)
  const [progressMessage, setProgressMessage] = useState('')
  const [error, setError] = useState(null)
  const progressTimerRef = useRef(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim()) {
      setError('Name is required')
      return
    }
    if (!file && !text.trim()) {
      setError('Upload a file or paste text content')
      return
    }

    setUploading(true)
    setError(null)
    setProgressMessage('Starting upload…')
    setShowProgress(false)
    progressTimerRef.current = setTimeout(() => setShowProgress(true), 1000)

    try {
      const form = new FormData()
      form.append('name', name.trim())
      form.append('description', description.trim())
      form.append('category', category)
      form.append('username', username || 'demo-user')
      if (file) {
        form.append('file', file)
      } else {
        form.append('text', text.trim())
      }

      const res = await fetch(`${API_URL}/admin/datasets/upload/stream`, {
        method: 'POST',
        body: form,
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.error || 'Upload failed')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let completePayload = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.trim()) continue
          const event = JSON.parse(line)
          if (event.stage === 'error') {
            throw new Error(event.message)
          }
          if (event.stage === 'complete') {
            completePayload = event
          } else if (event.message) {
            setProgressMessage(event.message)
          }
        }
      }

      if (!completePayload?.dataset_id) {
        throw new Error('Upload finished without dataset id')
      }
      onComplete(completePayload.dataset_id)
    } catch (err) {
      setError(String(err))
    } finally {
      clearTimeout(progressTimerRef.current)
      setUploading(false)
      setShowProgress(false)
    }
  }

  return (
    <div className="dataset-upload">
      <h2>New dataset</h2>
      <form onSubmit={handleSubmit} className="dataset-upload__form">
        <label className="form-field">
          <span>Name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={uploading}
            required
          />
        </label>

        <label className="form-field">
          <span>Description</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            disabled={uploading}
          />
        </label>

        <label className="form-field">
          <span>Category</span>
          <select value={category} onChange={(e) => setCategory(e.target.value)} disabled={uploading}>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </label>

        <label className="form-field">
          <span>File upload</span>
          <input
            type="file"
            accept=".json,.csv,.txt,.ndjson"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            disabled={uploading}
          />
        </label>

        <label className="form-field">
          <span>Or paste text / JSON</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            placeholder='[{"key": "value"}, ...] or free text'
            disabled={uploading}
          />
        </label>

        {showProgress && uploading && <ProgressBar message={progressMessage} />}

        {error && <p className="admin-error-text">{error}</p>}

        <div className="dataset-upload__actions">
          <button type="submit" className="btn-send" disabled={uploading}>
            {uploading ? 'Uploading…' : 'Upload dataset'}
          </button>
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={uploading}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}
