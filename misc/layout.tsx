import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AI Scraper — Intelligent Web Data Extraction',
  description: 'Extract structured datasets from any website using local AI. No API keys required.',
  keywords: ['web scraping', 'AI', 'data extraction', 'open source', 'local LLM'],
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        {children}
      </body>
    </html>
  )
}
