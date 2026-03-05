# Architecture Documentation

## Microservice Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CLIENT TIER                                     │
│                                                                        │
│   ┌─────────────────────────────────────────────────────────────┐     │
│   │                   Next.js 14 Frontend                       │     │
│   │                                                             │     │
│   │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │     │
│   │  │  ScrapeForm  │  │ JobProgress  │  │  ArchDiagram    │  │     │
│   │  │  Component   │  │  Component   │  │  Component      │  │     │
│   │  └──────┬───────┘  └──────┬───────┘  └─────────────────┘  │     │
│   │         │                 │                                 │     │
│   │  ┌──────▼─────────────────▼──────┐                         │     │
│   │  │         useScraper Hook       │                         │     │
│   │  │  (state machine + SSE client) │                         │     │
│   │  └──────────────┬────────────────┘                         │     │
│   │                 │ HTTP POST + SSE EventSource               │     │
│   └─────────────────┼───────────────────────────────────────────┘     │
└─────────────────────┼──────────────────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────────────────────┐
│                      APPLICATION TIER                                   │
│                                                                         │
│   ┌──────────────────────────────────────────────────────────────┐     │
│   │                    FastAPI Backend                            │     │
│   │                                                              │     │
│   │  POST /api/scrape ──► ScrapingPipeline (Background Task)    │     │
│   │  GET  /api/jobs/{id} ──► Job Status JSON                    │     │
│   │  GET  /api/jobs/{id}/stream ──► SSE Progress Stream         │     │
│   │  GET  /api/export/{id} ──► File Download                    │     │
│   │  DELETE /api/jobs/{id} ──► Cancel Job                       │     │
│   │                                                              │     │
│   │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │     │
│   │  │  Scraping   │  │  AI Engine   │  │  Export Service │   │     │
│   │  │  Service    │  │  Service     │  │                 │   │     │
│   │  │             │  │              │  │  ExcelExporter  │   │     │
│   │  │ Playwright  │  │ LLMService   │  │  WordExporter   │   │     │
│   │  │ BS4Parser   │  │ VectorStore  │  │                 │   │     │
│   │  │             │  │ Embeddings   │  │  Pandas         │   │     │
│   │  └─────────────┘  └──────────────┘  └─────────────────┘   │     │
│   └──────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────────────────────┐
│                     INFERENCE TIER                                      │
│                                                                         │
│   ┌────────────────────────┐    ┌────────────────────────────────┐     │
│   │   Ollama LLM Server    │    │   sentence-transformers        │     │
│   │   :11434               │    │   (in-process, no server)      │     │
│   │                        │    │                                │     │
│   │   Models:              │    │   Model: all-MiniLM-L6-v2      │     │
│   │   - tinyllama (~600MB) │    │   Dim: 384                     │     │
│   │   - phi (~1.7GB)       │    │   FAISS IndexFlatL2            │     │
│   └────────────────────────┘    └────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow (Sequence)

```
User                Frontend              Backend               Ollama
 │                      │                    │                     │
 │── Enter URL+Instr ──►│                    │                     │
 │                      │── POST /api/scrape►│                     │
 │                      │◄── job_id ─────────│                     │
 │                      │── SSE subscribe ──►│                     │
 │                      │                    │                     │
 │                      │◄─ [SCRAPING 20%] ──│ playwright.goto()   │
 │                      │◄─ [SCRAPING 30%] ──│ bs4.parse()         │
 │                      │◄─ [PROCESSING 55%]─│ st.encode()         │
 │                      │◄─ [PROCESSING 65%]─│ faiss.search()      │
 │                      │◄─ [PROCESSING 75%]─│──── chat() ────────►│
 │                      │                    │◄─── JSON rows ───────│
 │                      │◄─ [EXPORTING 88%]──│ pandas+openpyxl     │
 │                      │◄─ [COMPLETED 100%]─│                     │
 │◄─ Download button ───│                    │                     │
 │── Click download ───►│── GET /api/export ►│                     │
 │◄─ .xlsx / .docx ─────│◄─── FileResponse ──│                     │
```

## Job State Machine

```
  PENDING ──► SCRAPING ──► PROCESSING ──► EXPORTING ──► COMPLETED
     │            │              │              │
     └────────────┴──────────────┴──────────────┴──────► FAILED
                                                          CANCELLED
```

## Concurrency Model

- `asyncio.Semaphore(MAX_CONCURRENT_JOBS)` limits parallel jobs
- Each job runs in an `asyncio.Task` (non-blocking)
- SSE streams use `asyncio.Queue` per subscriber
- Playwright browser is instantiated per-job (safe for concurrency)
- FAISS + embeddings are per-job (not shared, avoids thread safety issues)
- Ollama handles its own concurrency server-side

## Scaling Notes

For production at scale, replace:
- In-memory `JobManager` → Redis + Celery workers
- In-memory file storage → S3-compatible object store
- Single Ollama → vLLM cluster or LiteLLM load balancer
- FAISS in-process → Qdrant or Weaviate dedicated service
