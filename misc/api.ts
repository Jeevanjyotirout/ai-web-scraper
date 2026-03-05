import type { ScrapeRequest, JobCreatedResponse, JobStatusResponse, ProgressEvent } from '@/types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail || `HTTP ${res.status}`)
  }

  return res.json()
}

export const api = {
  startScrape: (data: ScrapeRequest) =>
    request<JobCreatedResponse>('/api/scrape', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getJob: (jobId: string) =>
    request<JobStatusResponse>(`/api/jobs/${jobId}`),

  cancelJob: (jobId: string) =>
    request<{ message: string }>(`/api/jobs/${jobId}`, { method: 'DELETE' }),

  getDownloadUrl: (jobId: string) =>
    `${API_BASE}/api/export/${jobId}`,

  health: () => request<{ status: string; version: string }>('/health'),
}

/**
 * Subscribe to SSE job progress stream.
 * Returns an unsubscribe function.
 */
export function subscribeToJob(
  jobId: string,
  onEvent: (event: ProgressEvent) => void,
  onError?: (error: Event) => void,
): () => void {
  const url = `${API_BASE}/api/jobs/${jobId}/stream`
  const es = new EventSource(url)

  es.onmessage = (e) => {
    try {
      const data: ProgressEvent = JSON.parse(e.data)
      onEvent(data)
      if (['completed', 'failed', 'cancelled'].includes(data.status)) {
        es.close()
      }
    } catch {
      // ignore parse errors
    }
  }

  if (onError) {
    es.onerror = onError
  }

  return () => es.close()
}
