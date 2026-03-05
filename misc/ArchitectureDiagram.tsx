'use client'

export function ArchitectureDiagram() {
  const steps = [
    { icon: '🌐', label: 'URL Input', sub: 'Next.js UI', color: '#7c3aed' },
    { icon: '🎭', label: 'Playwright', sub: 'JS Rendering', color: '#3b82f6' },
    { icon: '🧹', label: 'BeautifulSoup', sub: 'HTML Parsing', color: '#06b6d4' },
    { icon: '🔢', label: 'Embeddings', sub: 'sentence-transformers', color: '#8b5cf6' },
    { icon: '🗄️', label: 'FAISS', sub: 'Vector Search', color: '#a855f7' },
    { icon: '🤖', label: 'TinyLlama', sub: 'Data Extraction', color: '#ec4899' },
    { icon: '📊', label: 'Export', sub: 'Excel / Word', color: '#00ffa3' },
  ]

  return (
    <div className="rounded-2xl border border-surface-border bg-surface-raised p-6">
      <h3 className="text-xs font-mono uppercase tracking-widest text-purple-300 mb-5">
        Pipeline Architecture
      </h3>
      <div className="flex flex-wrap items-center gap-2">
        {steps.map((step, i) => (
          <div key={i} className="flex items-center gap-2">
            <div
              className="flex flex-col items-center gap-1 px-3 py-2.5 rounded-xl border text-center min-w-[80px]"
              style={{ borderColor: `${step.color}40`, background: `${step.color}10` }}
            >
              <span className="text-lg">{step.icon}</span>
              <span className="text-xs font-bold text-white leading-tight">{step.label}</span>
              <span className="text-[10px] font-mono leading-tight" style={{ color: step.color }}>
                {step.sub}
              </span>
            </div>
            {i < steps.length - 1 && (
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="flex-shrink-0">
                <path d="M4 10h12M12 5l5 5-5 5" stroke="#4a4a7a" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
