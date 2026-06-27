import React from 'react'

export default function ProgressBar({ message }) {
  return (
    <div className="progress-bar-wrap">
      <div className="progress-bar">
        <div className="progress-bar__fill" />
      </div>
      {message && <p className="progress-bar__message">{message}</p>}
    </div>
  )
}
