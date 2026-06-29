import React from 'react'
import JsonViewer from '../JsonViewer'

export default function RecordCard({ record }) {
  return (
    <div className="record-card">
      <div className="record-card__header">
        <span className="record-card__index">#{record.row_index + 1}</span>
      </div>
      <JsonViewer data={record.data} variant="light" maxHeight={360} />
    </div>
  )
}
