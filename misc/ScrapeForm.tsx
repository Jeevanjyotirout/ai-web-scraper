'use client'

import { useState, FormEvent } from 'react'
import { Globe, FileSpreadsheet, FileText, Zap, ChevronDown } from 'lucide-react'
import type { OutputFormat } from '@/types'

interface ScrapeFormProps {
  onSubmit: (data: { url: string; instructions: string; output_format: OutputFormat; max_pages: number }) => void
  isRunning: boolean
  onCancel: () => void
}

const EXAMPLE_INSTRUCTIONS = [
  "Extract all product names, prices, and ratings",
  "Get all article titles, authors, dates, and summaries",
  "Collect all job listings with title, company, location, and salary",
  "Extract all team member names, roles, and bios",
  "Get all research papers with title, abstract, and authors",
]

export function ScrapeForm({ onSubmit, isRunning, onCancel }: ScrapeFormProps) {
  const [url, setUrl] = useState('')
  const [instructions, setInstructions] = useState('')
  const [outputFormat, setOutputFormat] = useState<OutputFormat>('excel')
  const [maxPages, setMaxPages] = useState(1)
  const [showExamples, setShowExamples] = useState(false)

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!url.trim() || !instructions.trim()) return
    onSubmit({
      url: url.trim(),
      instructions: instructions.trim(),
      output_format: outputFormat,
      max_pages: maxPages,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* URL Input */}
      <div>
        <label className="block text-xs font-mono uppercase tracking-widest text-purple-300 mb-2">
          Target URL
        </label>
        <div className="relative">
          <Globe className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-purple-400" />
          <input
            type="url"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://example.com"
            required
            disabled={isRunning}
            className="input-field w-full pl-11 pr-4 py-3.5 rounded-xl text-sm font-mono placeholder:text-gray-600 disabled:opacity-50"
          />
        </div>
      </div>

      {/* Instructions */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-xs font-mono uppercase tracking-widest text-purple-300">
            Extraction Instructions
          </label>
          <button
            type="button"
            onClick={() => setShowExamples(!showExamples)}
            className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1 transition-colors"
          >
            Examples <ChevronDown className={`w-3 h-3 transition-transform ${showExamples ? 'rotate-180' : ''}`} />
          </button>
        </div>

        {showExamples && (
          <div className="mb-3 rounded-xl border border-surface-border overflow-hidden">
            {EXAMPLE_INSTRUCTIONS.map((ex, i) => (
              <button
                key={i}
                type="button"
                onClick={() => { setInstructions(ex); setShowExamples(false) }}
                className="w-full text-left px-4 py-2.5 text-xs text-gray-300 hover:bg-surface-overlay hover:text-white transition-colors border-b border-surface-border last:border-0 font-mono"
              >
                → {ex}
              </button>
            ))}
          </div>
        )}

        <textarea
          value={instructions}
          onChange={e => setInstructions(e.target.value)}
          placeholder="Describe what data to extract — e.g. 'Extract all product names, prices, and descriptions from this e-commerce page'"
          required
          disabled={isRunning}
          rows={4}
          className="input-field w-full px-4 py-3.5 rounded-xl text-sm resize-none placeholder:text-gray-600 disabled:opacity-50"
        />
        <p className="text-xs text-gray-500 mt-1 font-mono">
          Be specific. The AI uses your instructions to extract and structure the data.
        </p>
      </div>

      {/* Output Format */}
      <div>
        <label className="block text-xs font-mono uppercase tracking-widest text-purple-300 mb-3">
          Output Format
        </label>
        <div className="grid grid-cols-2 gap-3">
          {([
            { value: 'excel', icon: FileSpreadsheet, label: 'Excel', desc: '.xlsx spreadsheet' },
            { value: 'word',  icon: FileText,        label: 'Word',  desc: '.docx document' },
          ] as const).map(({ value, icon: Icon, label, desc }) => (
            <button
              key={value}
              type="button"
              onClick={() => !isRunning && setOutputFormat(value)}
              disabled={isRunning}
              className={`relative flex items-center gap-3 p-4 rounded-xl border transition-all text-left disabled:opacity-50 ${
                outputFormat === value
                  ? 'border-purple-500 bg-purple-500/10'
                  : 'border-surface-border bg-surface-raised hover:border-purple-500/50'
              }`}
            >
              <Icon className={`w-5 h-5 ${outputFormat === value ? 'text-purple-400' : 'text-gray-500'}`} />
              <div>
                <div className={`text-sm font-semibold ${outputFormat === value ? 'text-white' : 'text-gray-300'}`}>
                  {label}
                </div>
                <div className="text-xs text-gray-500 font-mono">{desc}</div>
              </div>
              {outputFormat === value && (
                <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-purple-400" style={{ boxShadow: '0 0 6px #c084fc' }} />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Max Pages */}
      <div>
        <label className="block text-xs font-mono uppercase tracking-widest text-purple-300 mb-2">
          Max Pages to Scrape: <span style={{ color: '#00ffa3' }}>{maxPages}</span>
        </label>
        <input
          type="range"
          min={1} max={10} step={1}
          value={maxPages}
          onChange={e => setMaxPages(Number(e.target.value))}
          disabled={isRunning}
          className="w-full accent-purple-500 disabled:opacity-50"
        />
        <div className="flex justify-between text-xs text-gray-600 font-mono mt-1">
          <span>1 page</span><span>10 pages</span>
        </div>
      </div>

      {/* Submit */}
      <div className="flex gap-3 pt-2">
        {isRunning ? (
          <button
            type="button"
            onClick={onCancel}
            className="w-full py-4 rounded-xl border border-red-500/50 text-red-400 hover:bg-red-500/10 transition-all font-semibold text-sm"
          >
            Cancel Job
          </button>
        ) : (
          <button
            type="submit"
            className="btn-primary w-full py-4 rounded-xl text-sm font-bold tracking-wide flex items-center justify-center gap-2 relative z-10"
          >
            <Zap className="w-4 h-4" />
            Start Extraction
          </button>
        )}
      </div>
    </form>
  )
}
