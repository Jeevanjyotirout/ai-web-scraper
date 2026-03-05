'use client'

import { useEffect, useRef } from 'react'
import { Download, RotateCcw, Terminal, CheckCircle, XCircle, Rows3 } from 'lucide-react'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { StatusBadge } from '@/components/ui/StatusBadge'
import type { ScrapeState } from '@/hooks/useScraper'

interface JobProgressProps {
  state: ScrapeState
  downloadUrl: string | null
  onReset: () => void
  logs: string[]
}

export function JobProgress({ state, downloadUrl, onReset, logs }: JobProgressProps) {
  const logsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight
    }
  }, [logs])

  const isComplete = state.status === 'completed'
  const isFailed = state.status === 'failed'
  const isDone = isComplete || isFailed || state.status === 'cancelled'

  return (
    <div className="space-y-5 animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Terminal className="w-5 h-5 text-purple-400" />
          <span className="font-display font-bold text-lg">Extraction Progress</span>
        </div>
        {state.status && <StatusBadge status={state.status} pulse={state.isRunning} />}
      </div>

      {/* Progress Bar */}
      <ProgressBar progress={state.progress} />

      {/* Current Message */}
      <div className="rounded-xl bg-surface-overlay border border-surface-border px-4 py-3">
        <p className="text-sm font-mono text-gray-300 flex items-center gap-2">
          {state.isRunning && (
            <span className="w-2 h-2 rounded-full bg-purple-400 animate-pulse inline-block" />
          )}
          {state.message || 'Initializing...'}
        </p>
        {state.step && (
          <p className="text-xs text-gray-600 font-mono mt-1">step: {state.step}</p>
        )}
      </div>

      {/* Terminal Logs */}
      <div
        ref={logsRef}
        className="rounded-xl bg-black/50 border border-surface-border p-4 h-48 overflow-y-auto terminal relative"
      >
        <div className="scan-line opacity-20 pointer-events-none" />
        {logs.length === 0 ? (
          <p className="text-gray-600">$ waiting for output...</p>
        ) : (
          logs.map((log, i) => (
            <div key={i} className="text-xs leading-relaxed">
              <span className="text-purple-500 select-none">{'>'} </span>
              <span className="text-gray-300">{log}</span>
            </div>
          ))
        )}
        {state.isRunning && (
          <div className="text-xs mt-1">
            <span className="text-purple-500">{'>'} </span>
            <span className="text-green-400 animate-pulse">█</span>
          </div>
        )}
      </div>

      {/* Success State */}
      {isComplete && (
        <div className="rounded-xl border p-5 space-y-4" style={{ borderColor: 'rgba(0,255,163,0.3)', background: 'rgba(0,255,163,0.05)' }}>
          <div className="flex items-center gap-3">
            <CheckCircle className="w-6 h-6" style={{ color: '#00ffa3' }} />
            <div>
              <p className="font-bold text-white">Extraction Complete!</p>
              {state.rows != null && (
                <p className="text-sm font-mono flex items-center gap-1.5 mt-0.5" style={{ color: '#00ffa3' }}>
                  <Rows3 className="w-3.5 h-3.5" />
                  {state.rows.toLocaleString()} rows extracted
                </p>
              )}
            </div>
          </div>

          <div className="flex gap-3">
            {downloadUrl && (
              <a
                href={downloadUrl}
                download
                className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-bold text-sm text-black transition-all hover:opacity-90"
                style={{ background: 'linear-gradient(135deg, #00ffa3, #00d4ff)' }}
              >
                <Download className="w-4 h-4" />
                Download File
              </a>
            )}
            <button
              onClick={onReset}
              className="px-4 py-3 rounded-xl border border-surface-border text-gray-400 hover:text-white hover:border-gray-500 transition-all"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Error State */}
      {isFailed && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-5 space-y-3">
          <div className="flex items-center gap-3">
            <XCircle className="w-5 h-5 text-red-400" />
            <p className="font-bold text-red-300">Extraction Failed</p>
          </div>
          {state.error && (
            <p className="text-xs font-mono text-red-400/80 bg-black/30 p-3 rounded-lg">
              {state.error}
            </p>
          )}
          <button
            onClick={onReset}
            className="w-full py-2.5 rounded-xl border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-all text-sm font-semibold flex items-center justify-center gap-2"
          >
            <RotateCcw className="w-4 h-4" /> Try Again
          </button>
        </div>
      )}

      {/* Cancelled */}
      {state.status === 'cancelled' && (
        <button
          onClick={onReset}
          className="w-full py-3 rounded-xl border border-surface-border text-gray-400 hover:text-white transition-all text-sm font-semibold flex items-center justify-center gap-2"
        >
          <RotateCcw className="w-4 h-4" /> Start New Extraction
        </button>
      )}
    </div>
  )
}
