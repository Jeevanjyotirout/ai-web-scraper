'use client'

import { useState, useCallback } from 'react'
import { Bot, Cpu, Shield, Github, BookOpen, Layers } from 'lucide-react'
import { ScrapeForm } from '@/components/scraper/ScrapeForm'
import { JobProgress } from '@/components/scraper/JobProgress'
import { ArchitectureDiagram } from '@/components/layout/ArchitectureDiagram'
import { useScraper } from '@/hooks/useScraper'
import type { ProgressEvent } from '@/types'

const FEATURES = [
  { icon: Bot, title: 'Local AI', desc: 'TinyLlama / Phi running on your hardware', color: '#7c3aed' },
  { icon: Shield, title: 'No API Keys', desc: '100% free, open-source, private', color: '#00ffa3' },
  { icon: Cpu, title: 'FAISS + ST', desc: 'Semantic vector search for smart extraction', color: '#00d4ff' },
  { icon: Layers, title: 'Any Format', desc: 'Export as Excel or Word documents', color: '#a855f7' },
]

export default function HomePage() {
  const { state, start, cancel, reset, downloadUrl } = useScraper()
  const [logs, setLogs] = useState<string[]>([])

  const handleStart = useCallback(async (data: Parameters<typeof start>[0]) => {
    setLogs([])
    await start(data)
  }, [start])

  const handleReset = useCallback(() => {
    setLogs([])
    reset()
  }, [reset])

  // Intercept the progress events to build a log
  // We patch the hook state via a wrapper
  const handleEvent = useCallback((event: ProgressEvent) => {
    setLogs(prev => {
      const line = `[${event.status.toUpperCase()}] ${event.message}`
      if (prev[prev.length - 1] === line) return prev
      return [...prev, line]
    })
  }, [])

  const isIdle = !state.isRunning && !state.status
  const showProgress = !!state.status

  return (
    <div className="min-h-screen bg-grid relative overflow-hidden">
      {/* Ambient background blobs */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 w-96 h-96 rounded-full opacity-20"
          style={{ background: 'radial-gradient(circle, #7c3aed 0%, transparent 70%)', filter: 'blur(60px)' }} />
        <div className="absolute -bottom-40 -right-40 w-96 h-96 rounded-full opacity-15"
          style={{ background: 'radial-gradient(circle, #00ffa3 0%, transparent 70%)', filter: 'blur(60px)' }} />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full opacity-5"
          style={{ background: 'radial-gradient(circle, #00d4ff 0%, transparent 70%)', filter: 'blur(80px)' }} />
      </div>

      <div className="relative z-10 max-w-6xl mx-auto px-4 py-12">
        {/* Header */}
        <header className="text-center mb-14 animate-fade-in">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-purple-500/30 bg-purple-500/10 text-xs font-mono text-purple-300 uppercase tracking-widest mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
            Open Source · Local AI · No API Keys
          </div>

          <h1 className="text-6xl md:text-7xl font-display font-extrabold tracking-tight mb-4">
            <span className="text-white">AI</span>
            <span className="mx-3" style={{
              background: 'linear-gradient(135deg, #7c3aed, #00ffa3)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>Scraper</span>
          </h1>

          <p className="text-lg text-gray-400 max-w-xl mx-auto leading-relaxed font-body">
            Extract structured datasets from any website using local AI.
            <br />
            <span className="text-gray-500">Powered by TinyLlama, FAISS & Playwright.</span>
          </p>

          {/* Nav links */}
          <div className="flex items-center justify-center gap-4 mt-6">
            <a
              href="https://github.com/your-repo/ai-scraper"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors"
            >
              <Github className="w-4 h-4" /> GitHub
            </a>
            <span className="text-gray-700">·</span>
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors"
            >
              <BookOpen className="w-4 h-4" /> API Docs
            </a>
          </div>
        </header>

        {/* Feature Pills */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
          {FEATURES.map(({ icon: Icon, title, desc, color }) => (
            <div
              key={title}
              className="card p-4 flex flex-col gap-2 hover:border-purple-500/40 transition-all"
            >
              <Icon className="w-5 h-5" style={{ color }} />
              <div>
                <p className="font-semibold text-sm text-white">{title}</p>
                <p className="text-xs text-gray-500 leading-snug">{desc}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Main Layout: Form + Progress */}
        <div className="grid md:grid-cols-2 gap-6 mb-10">
          {/* Left: Form */}
          <div className="gradient-border">
            <div className="card rounded-[15px] p-6 h-full">
              <div className="flex items-center gap-2 mb-6">
                <div className="w-2 h-2 rounded-full bg-red-500" />
                <div className="w-2 h-2 rounded-full bg-yellow-500" />
                <div className="w-2 h-2 rounded-full" style={{ background: '#00ffa3' }} />
                <span className="ml-2 text-xs font-mono text-gray-600">scraper.config</span>
              </div>
              <ScrapeForm
                onSubmit={handleStart}
                isRunning={state.isRunning}
                onCancel={cancel}
              />
            </div>
          </div>

          {/* Right: Progress / Placeholder */}
          <div className="card p-6">
            {!showProgress ? (
              <div className="h-full flex flex-col items-center justify-center text-center py-8">
                <div className="w-20 h-20 rounded-2xl border border-surface-border flex items-center justify-center mb-4"
                  style={{ background: 'rgba(124,58,237,0.1)' }}>
                  <Bot className="w-10 h-10 text-purple-400" />
                </div>
                <h3 className="font-display font-bold text-xl mb-2 text-white">Ready to Extract</h3>
                <p className="text-sm text-gray-500 max-w-xs leading-relaxed">
                  Configure your scraping job on the left and click{' '}
                  <span className="text-purple-400">"Start Extraction"</span>.
                  Live progress will appear here.
                </p>
                <div className="mt-6 grid grid-cols-3 gap-3 w-full max-w-xs">
                  {['Scrape', 'Embed', 'Export'].map((step, i) => (
                    <div key={step} className="flex flex-col items-center gap-1">
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold font-mono"
                        style={{ background: 'rgba(124,58,237,0.2)', color: '#c084fc', border: '1px solid rgba(124,58,237,0.3)' }}
                      >
                        {i + 1}
                      </div>
                      <span className="text-[10px] text-gray-600 font-mono">{step}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <JobProgress
                state={state}
                downloadUrl={downloadUrl}
                onReset={handleReset}
                logs={logs}
              />
            )}
          </div>
        </div>

        {/* Architecture Diagram */}
        <ArchitectureDiagram />

        {/* Footer */}
        <footer className="mt-12 text-center">
          <p className="text-xs text-gray-700 font-mono">
            MIT License · Built with Next.js, FastAPI, Playwright, sentence-transformers, FAISS, TinyLlama
          </p>
        </footer>
      </div>
    </div>
  )
}
