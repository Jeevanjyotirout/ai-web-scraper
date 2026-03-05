'use client'

import { useState, useCallback, useRef } from 'react'
import { api, subscribeToJob } from '@/lib/api'
import type { ScrapeRequest, ProgressEvent, JobStatus } from '@/types'

export interface ScrapeState {
  jobId: string | null
  status: JobStatus | null
  progress: number
  message: string
  step: string
  error: string | null
  rows: number | null
  filename: string | null
  isRunning: boolean
}

const INITIAL_STATE: ScrapeState = {
  jobId: null,
  status: null,
  progress: 0,
  message: '',
  step: '',
  error: null,
  rows: null,
  filename: null,
  isRunning: false,
}

export function useScraper() {
  const [state, setState] = useState<ScrapeState>(INITIAL_STATE)
  const unsubscribeRef = useRef<(() => void) | null>(null)

  const start = useCallback(async (request: ScrapeRequest) => {
    // Cancel any running job
    if (unsubscribeRef.current) {
      unsubscribeRef.current()
      unsubscribeRef.current = null
    }

    setState({ ...INITIAL_STATE, isRunning: true, status: 'pending', message: 'Starting...' })

    try {
      const created = await api.startScrape(request)

      setState(prev => ({
        ...prev,
        jobId: created.job_id,
        status: created.status,
      }))

      // Subscribe to SSE events
      const unsub = subscribeToJob(
        created.job_id,
        (event: ProgressEvent) => {
          setState(prev => ({
            ...prev,
            status: event.status,
            progress: event.progress,
            message: event.message,
            step: event.step,
            error: event.error ?? null,
            rows: (event.data as Record<string, number> | null)?.rows ?? prev.rows,
            filename: (event.data as Record<string, string> | null)?.filename ?? prev.filename,
            isRunning: !['completed', 'failed', 'cancelled'].includes(event.status),
          }))
        },
        () => {
          setState(prev => ({
            ...prev,
            isRunning: false,
            error: prev.error ?? 'Connection lost',
          }))
        }
      )

      unsubscribeRef.current = unsub
    } catch (err) {
      setState(prev => ({
        ...prev,
        isRunning: false,
        status: 'failed',
        error: err instanceof Error ? err.message : 'Unknown error',
        message: 'Failed to start job',
      }))
    }
  }, [])

  const cancel = useCallback(async () => {
    if (unsubscribeRef.current) {
      unsubscribeRef.current()
      unsubscribeRef.current = null
    }
    if (state.jobId) {
      try { await api.cancelJob(state.jobId) } catch { /* ignore */ }
    }
    setState(prev => ({ ...prev, isRunning: false, status: 'cancelled' }))
  }, [state.jobId])

  const reset = useCallback(() => {
    if (unsubscribeRef.current) {
      unsubscribeRef.current()
      unsubscribeRef.current = null
    }
    setState(INITIAL_STATE)
  }, [])

  const downloadUrl = state.jobId && state.status === 'completed'
    ? api.getDownloadUrl(state.jobId)
    : null

  return { state, start, cancel, reset, downloadUrl }
}
