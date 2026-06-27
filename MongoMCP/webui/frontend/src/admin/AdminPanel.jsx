import React, { useState } from 'react'
import DatasetList from './DatasetList'
import DatasetUpload from './DatasetUpload'
import DatasetDetail from './DatasetDetail'

export default function AdminPanel({ username }) {
  const [view, setView] = useState('list')
  const [selectedId, setSelectedId] = useState(null)

  function handleSelect(id) {
    setSelectedId(id)
    setView('detail')
  }

  function handleUploadComplete(datasetId) {
    setSelectedId(datasetId)
    setView('detail')
  }

  function handleBack() {
    setSelectedId(null)
    setView('list')
  }

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <nav>
          <button
            type="button"
            className={`admin-sidebar__item ${view !== 'detail' || selectedId ? 'admin-sidebar__item--active' : ''}`}
            onClick={() => { setView('list'); setSelectedId(null) }}
          >
            Datasets
          </button>
        </nav>
      </aside>
      <main className="admin-content">
        {view === 'upload' && (
          <DatasetUpload
            username={username}
            onComplete={handleUploadComplete}
            onCancel={() => setView('list')}
          />
        )}
        {view === 'detail' && selectedId && (
          <DatasetDetail
            datasetId={selectedId}
            username={username}
            onBack={handleBack}
          />
        )}
        {view === 'list' && (
          <DatasetList
            onSelect={handleSelect}
            onNew={() => setView('upload')}
          />
        )}
      </main>
    </div>
  )
}
