export type OutputFormat = 'excel' | 'word'

export type JobStatus =
  | 'pending'
  | 'scraping'
  | 'processing'
  | 'exporting'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface ScrapeRequest {
  url: string
  instructions: string
  output_format: OutputFormat
  max_pages?: number
}

export interface JobCreatedResponse {
  job_id: string
  status: JobStatus
  message: string
  created_at: string
}

export interface ProgressEvent {
  job_id: string
  status: JobStatus
  progress: number
  message: string
  step: string
  data?: Record<string, unknown> | null
  error?: string | null
}

export interface JobStatusResponse {
  job_id: string
  status: JobStatus
  progress: number
  message: string
  url: string
  instructions: string
  output_format: OutputFormat
  created_at: string
  updated_at: string
  completed_at?: string | null
  error?: string | null
  rows_extracted?: number | null
  file_size_bytes?: number | null
}

export const STATUS_LABELS: Record<JobStatus, string> = {
  pending: 'Queued',
  scraping: 'Scraping',
  processing: 'Processing',
  exporting: 'Exporting',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

export const STATUS_COLORS: Record<JobStatus, string> = {
  pending: 'text-yellow-400',
  scraping: 'text-blue-400',
  processing: 'text-purple-400',
  exporting: 'text-cyan-400',
  completed: 'text-green-400',
  failed: 'text-red-400',
  cancelled: 'text-gray-400',
}
