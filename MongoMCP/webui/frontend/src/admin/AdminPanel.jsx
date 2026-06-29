import React, { useState } from 'react'
import DatasetList from './DatasetList'
import DatasetUpload from './DatasetUpload'
import DatasetDetail from './DatasetDetail'
import UserMemory from './UserMemory'

export default function AdminPanel({ username, authUser }) {
  const [section, setSection] = useState('datasets')
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
            className={`admin-sidebar__item ${section === 'datasets' ? 'admin-sidebar__item--active' : ''}`}
            onClick={() => { setSection('datasets'); setView('list'); setSelectedId(null) }}
          >
            Datasets
          </button>
          <button
            type="button"
            className={`admin-sidebar__item ${section === 'user-memory' ? 'admin-sidebar__item--active' : ''}`}
            onClick={() => { setSection('user-memory'); setView('list'); setSelectedId(null) }}
          >
            User Memory
          </button>
        </nav>
      </aside>
      <main className="admin-content">
        {section === 'user-memory' && (
          <UserMemory username={username} authUser={authUser} />
        )}
        {section === 'datasets' && view === 'upload' && (
          <DatasetUpload
            username={username}
            onComplete={handleUploadComplete}
            onCancel={() => setView('list')}
          />
        )}
        {section === 'datasets' && view === 'detail' && selectedId && (
          <DatasetDetail
            datasetId={selectedId}
            username={username}
            onBack={handleBack}
          />
        )}
        {section === 'datasets' && view === 'list' && (
          <DatasetList
            onSelect={handleSelect}
            onNew={() => setView('upload')}
          />
        )}
      </main>
    </div>
  )
}
