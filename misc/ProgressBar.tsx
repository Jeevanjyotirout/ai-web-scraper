'use client'

interface ProgressBarProps {
  progress: number
  className?: string
  showLabel?: boolean
}

export function ProgressBar({ progress, className = '', showLabel = true }: ProgressBarProps) {
  return (
    <div className={`w-full ${className}`}>
      {showLabel && (
        <div className="flex justify-between items-center mb-2">
          <span className="text-xs text-purple-300 font-mono uppercase tracking-widest">Progress</span>
          <span className="text-xs font-mono text-neon-green font-bold" style={{ color: '#00ffa3' }}>
            {progress}%
          </span>
        </div>
      )}
      <div className="h-2 bg-surface-overlay rounded-full overflow-hidden relative">
        {/* Background shimmer */}
        <div className="absolute inset-0 shimmer opacity-30" />
        {/* Actual progress */}
        <div
          className="h-full rounded-full progress-bar relative"
          style={{ width: `${progress}%` }}
        >
          {/* Leading glow dot */}
          <div
            className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full"
            style={{
              background: '#00ffa3',
              boxShadow: '0 0 8px #00ffa3, 0 0 16px #00ffa3',
              opacity: progress > 0 ? 1 : 0,
            }}
          />
        </div>
      </div>
    </div>
  )
}
