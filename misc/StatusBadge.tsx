'use client'

import type { JobStatus } from '@/types'
import { STATUS_LABELS } from '@/types'

const COLOR_MAP: Record<JobStatus, { bg: string; text: string; dot: string }> = {
  pending:    { bg: 'rgba(234,179,8,0.12)',   text: '#eab308', dot: '#eab308' },
  scraping:   { bg: 'rgba(59,130,246,0.12)',  text: '#60a5fa', dot: '#60a5fa' },
  processing: { bg: 'rgba(168,85,247,0.12)',  text: '#c084fc', dot: '#c084fc' },
  exporting:  { bg: 'rgba(6,182,212,0.12)',   text: '#22d3ee', dot: '#22d3ee' },
  completed:  { bg: 'rgba(0,255,163,0.12)',   text: '#00ffa3', dot: '#00ffa3' },
  failed:     { bg: 'rgba(239,68,68,0.12)',   text: '#f87171', dot: '#f87171' },
  cancelled:  { bg: 'rgba(107,114,128,0.12)', text: '#9ca3af', dot: '#9ca3af' },
}

interface StatusBadgeProps {
  status: JobStatus
  pulse?: boolean
}

export function StatusBadge({ status, pulse = false }: StatusBadgeProps) {
  const c = COLOR_MAP[status]
  const isActive = ['pending', 'scraping', 'processing', 'exporting'].includes(status)

  return (
    <span
      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold uppercase tracking-widest"
      style={{ background: c.bg, color: c.text }}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${isActive && pulse ? 'animate-pulse' : ''}`}
        style={{ background: c.dot, boxShadow: `0 0 6px ${c.dot}` }}
      />
      {STATUS_LABELS[status]}
    </span>
  )
}
