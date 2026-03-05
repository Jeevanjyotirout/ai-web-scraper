# DataVault — AI Web Scraper · Docker Deployment

> **Full-stack containerised deployment** for the DataVault AI scraping platform.  
> Services: Nginx · Next.js · FastAPI · Celery · Redis · Qdrant · Ollama

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     PUBLIC NETWORK                       │
│                                                          │
│   Browser  ─────────────►  Nginx (80/443)               │
│                              │                           │
└──────────────────────────────┼──────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────┐
│                  INTERNAL NETWORK                         │
│                              │                           │
│          ┌───────────────────┼──────────────┐            │
│          ▼                   ▼              ▼            │
│      Frontend           Backend API      Ollama          │
│     (Next.js)           (FastAPI)     (Local LLM)        │
│       :3000              :8000          :11434           │
│                             │                           │
│              ┌──────────────┼──────────────┐            │
│              ▼              ▼              ▼            │
│           Redis          Qdrant        Celery           │
│          :6379         :6333/:6334     Workers          │
│       (Cache+Queue)   (Vector DB)   (Async Jobs)        │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## Prerequisites

| Tool | Min Version | Install |
|------|------------|---------|
| Docker | 24.0 | [docs.docker.com](https://docs.docker.com/get-docker/) |
| Docker Compose | v2 plugin | bundled with Docker Desktop |
| RAM | 8 GB (16 GB recommended for LLM) | — |
| Disk | 20 GB free | — |

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/your-org/datavault.git
cd datavault

# Auto-setup (generates secrets, builds images, starts stack, pulls LLM)
chmod +x scripts/setup.sh
./scripts/setup.sh setup
```

That's it. Open **https://localhost** in your browser.

---

### 2. Manual setup (step-by-step)

```bash
# Copy env template and edit values
cp .env.example .env
$EDITOR .env

# Build images
docker compose build --parallel

# Start infrastructure first
docker compose up -d redis qdrant

# Start remaining services
docker compose up -d

# Pull your chosen LLM (see model options below)
docker compose exec ollama ollama pull mistral

# Initialize Qdrant vector collections
./scripts/setup.sh init-qdrant
```

---

## Service Reference

### Redis `redis:7.2-alpine`
- **Role**: Job queue broker, result backend, session cache
- **Persistence**: AOF + RDB snapshots every 60s
- **Memory limit**: 512 MB with LRU eviction
- **Databases**: `0` = cache, `1` = Celery broker, `2` = results

### Qdrant `qdrant/qdrant:v1.9.2`
- **Role**: Vector database for semantic search over scraped content
- **REST API**: `:6333` | **gRPC**: `:6334`
- **Dashboard**: http://localhost:6333/dashboard *(dev only)*
- **Collections auto-created**: `scrape_embeddings`, `document_chunks`, `entity_store`

### Ollama `ollama/ollama:latest`
- **Role**: Runs LLMs locally for instruction parsing and entity extraction
- **Default model**: `mistral` (~4 GB)

**Available models** (change `OLLAMA_MODEL` in `.env`):

| Model | Size | Best for |
|-------|------|----------|
| `mistral` | 4.1 GB | General purpose (default) |
| `llama3` | 4.7 GB | Instruction following |
| `phi3` | 2.3 GB | Low RAM environments |
| `gemma2` | 5.4 GB | Reasoning & analysis |
| `codellama` | 3.8 GB | Code/structured extraction |

```bash
# Pull a different model
OLLAMA_MODEL=llama3 ./scripts/setup.sh pull-model

# Or directly
docker compose exec ollama ollama pull llama3
```

**GPU acceleration** (NVIDIA): uncomment the `deploy.resources` block in `docker-compose.yml` for the `ollama` service. Requires [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

---

## Common Operations

```bash
# View all service status + resource usage
./scripts/setup.sh status

# Tail logs
./scripts/setup.sh logs              # all services
./scripts/setup.sh logs backend      # specific service
./scripts/setup.sh logs worker       # Celery worker

# Restart a service after code change
./scripts/setup.sh restart backend

# Stop (preserves data volumes)
./scripts/setup.sh stop

# Full teardown including volumes
./scripts/setup.sh destroy
```

### Enable monitoring (Flower)

Flower is included but gated behind a Docker Compose profile.

```bash
# Start with monitoring
docker compose --profile monitoring up -d

# Access at http://localhost:5555
# Default login: admin / flowerpass  (set FLOWER_USER/PASS in .env)
```

---

## Configuration

All configuration is via `.env`. Key variables:

```env
OLLAMA_MODEL=mistral          # LLM model name
WORKER_REPLICAS=2             # Number of Celery worker containers
MAX_CONCURRENT_JOBS=5         # Parallel scraping jobs
REDIS_PASSWORD=<strong-pass>  # Redis auth password
```

---

## Production Checklist

- [ ] Replace self-signed TLS cert in `nginx/ssl/` with a real certificate (Let's Encrypt / ACM)
- [ ] Set strong unique values for all `*_PASSWORD`, `SECRET_KEY`, `NEXTAUTH_SECRET` in `.env`
- [ ] Set `ALLOWED_ORIGINS` to your real domain(s)
- [ ] Consider mounting volumes on dedicated block storage for `qdrant_data` and `ollama_models`
- [ ] Set up log aggregation (Loki / CloudWatch / Datadog)
- [ ] Configure external Redis (ElastiCache) for multi-node deployments
- [ ] Add backup cron for Qdrant: `docker compose exec qdrant qdrant-snapshot`
- [ ] Remove or firewall `:6379`, `:6333`, `:11434` ports in production

---

## Directory Structure

```
datavault/
├── docker-compose.yml          # Production stack
├── docker-compose.override.yml # Dev overrides (auto-loaded)
├── .env.example                # Environment template
├── config/
│   └── qdrant.yaml             # Qdrant tuning config
├── frontend/
│   └── Dockerfile              # Next.js multi-stage build
├── backend/
│   ├── Dockerfile              # FastAPI multi-stage build
│   └── requirements.txt        # Python dependencies
├── nginx/
│   ├── Dockerfile
│   ├── nginx.conf              # Main nginx config
│   └── conf.d/
│       └── datavault.conf      # Virtual host + proxy rules
└── scripts/
    └── setup.sh                # Setup & operations CLI
```

---

## Troubleshooting

**Ollama is slow / OOM**  
Lower parallelism: set `OLLAMA_NUM_PARALLEL=1` in `.env` and use a smaller model like `phi3`.

**Qdrant collection errors**  
Re-run `./scripts/setup.sh init-qdrant` after the qdrant service is healthy.

**Backend won't start**  
Check Redis is healthy first: `docker compose ps redis`. Verify `REDIS_PASSWORD` matches in `.env`.

**Port conflicts**  
Edit the `ports:` mappings in `docker-compose.override.yml` for your dev machine.

**Out of disk space**  
Prune unused images/volumes: `docker system prune -a --volumes`
