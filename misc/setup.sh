#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  DataVault — Setup & Operations Script
#  Usage: ./scripts/setup.sh [command]
# ══════════════════════════════════════════════════════════════════

set -euo pipefail

COMPOSE="docker compose"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }

banner() {
  echo -e "${BOLD}${CYAN}"
  echo "  ██████╗  █████╗ ████████╗ █████╗ ██╗   ██╗ █████╗ ██╗   ██╗██╗  ████████╗"
  echo "  ██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗██║   ██║██╔══██╗██║   ██║██║  ╚══██╔══╝"
  echo "  ██║  ██║███████║   ██║   ███████║██║   ██║███████║██║   ██║██║     ██║   "
  echo "  ██║  ██║██╔══██║   ██║   ██╔══██║╚██╗ ██╔╝██╔══██║██║   ██║██║     ██║   "
  echo "  ██████╔╝██║  ██║   ██║   ██║  ██║ ╚████╔╝ ██║  ██║╚██████╔╝███████╗██║   "
  echo "  ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝  ╚═══╝  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝   "
  echo -e "${RESET}"
}

# ── Prerequisites check ───────────────────────────────────────────────────────
check_prereqs() {
  info "Checking prerequisites..."
  for cmd in docker git curl; do
    command -v "$cmd" &>/dev/null || error "$cmd is required but not installed."
  done
  docker info &>/dev/null || error "Docker daemon is not running."
  # Check Docker Compose v2
  docker compose version &>/dev/null || error "Docker Compose v2 plugin required."
  # Check min Docker version (24+)
  DOCKER_VER=$(docker version --format '{{.Server.Version}}' | cut -d. -f1)
  [[ "$DOCKER_VER" -ge 24 ]] || warn "Docker 24+ recommended (found $DOCKER_VER)"
  success "Prerequisites OK"
}

# ── Environment setup ─────────────────────────────────────────────────────────
setup_env() {
  info "Setting up environment..."
  if [[ ! -f .env ]]; then
    cp .env.example .env
    # Auto-generate secrets
    if command -v openssl &>/dev/null; then
      SECRET=$(openssl rand -hex 32)
      NEXTAUTH=$(openssl rand -hex 32)
      REDIS_PASS=$(openssl rand -hex 24)
      sed -i "s/replace_with_random_32_char_string_here/$SECRET/" .env
      sed -i "s/replace_with_random_secret/$NEXTAUTH/" .env
      sed -i "s/replace_with_strong_redis_password/$REDIS_PASS/" .env
      success "Secrets auto-generated"
    else
      warn ".env created from template — fill in secrets manually"
    fi
  else
    warn ".env already exists, skipping"
  fi
}

# ── Build images ──────────────────────────────────────────────────────────────
build() {
  info "Building Docker images (this may take a few minutes)..."
  $COMPOSE build --parallel "$@"
  success "Images built"
}

# ── Start stack ───────────────────────────────────────────────────────────────
start() {
  info "Starting DataVault stack..."
  $COMPOSE up -d "$@"
  success "Stack started"
  wait_healthy
}

# ── Wait for all services to be healthy ───────────────────────────────────────
wait_healthy() {
  info "Waiting for services to become healthy..."
  local services=(redis qdrant backend frontend nginx)
  local timeout=120
  for svc in "${services[@]}"; do
    local elapsed=0
    printf "  %-12s " "$svc"
    while true; do
      STATUS=$($COMPOSE ps --format json "$svc" 2>/dev/null | \
               python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Health',''))" 2>/dev/null || echo "")
      if [[ "$STATUS" == "healthy" ]]; then
        echo -e "${GREEN}healthy${RESET}"
        break
      elif [[ "$STATUS" == "unhealthy" ]]; then
        echo -e "${RED}unhealthy${RESET}"
        warn "Check logs: $COMPOSE logs $svc"
        break
      fi
      if [[ $elapsed -ge $timeout ]]; then
        echo -e "${YELLOW}timeout${RESET}"
        break
      fi
      sleep 3; elapsed=$((elapsed + 3))
      printf "."
    done
  done
}

# ── Pull Ollama model ─────────────────────────────────────────────────────────
pull_model() {
  local MODEL="${OLLAMA_MODEL:-mistral}"
  info "Pulling Ollama model: $MODEL (this may take several minutes)..."
  $COMPOSE exec ollama ollama pull "$MODEL"
  success "Model '$MODEL' ready"
}

# ── Init Qdrant collections ───────────────────────────────────────────────────
init_qdrant() {
  info "Initializing Qdrant collections..."
  $COMPOSE exec backend python3 -c "
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(host='qdrant', port=6333)
collections = ['scrape_embeddings', 'document_chunks', 'entity_store']
for col in collections:
    existing = [c.name for c in client.get_collections().collections]
    if col not in existing:
        client.create_collection(col, vectors_config=VectorParams(size=384, distance=Distance.COSINE))
        print(f'  Created collection: {col}')
    else:
        print(f'  Collection exists:  {col}')
print('Qdrant init complete.')
"
  success "Qdrant collections ready"
}

# ── Stop stack ────────────────────────────────────────────────────────────────
stop() {
  info "Stopping stack..."
  $COMPOSE down "$@"
  success "Stack stopped"
}

# ── Restart a specific service ────────────────────────────────────────────────
restart_svc() {
  local SVC="${1:-}"
  [[ -z "$SVC" ]] && error "Usage: $0 restart <service>"
  info "Restarting $SVC..."
  $COMPOSE restart "$SVC"
  success "$SVC restarted"
}

# ── Tail logs ─────────────────────────────────────────────────────────────────
logs() {
  $COMPOSE logs -f --tail=100 "${@:-}"
}

# ── Health summary ────────────────────────────────────────────────────────────
status() {
  echo ""
  echo -e "${BOLD}Service Status${RESET}"
  $COMPOSE ps
  echo ""
  echo -e "${BOLD}Resource Usage${RESET}"
  docker stats --no-stream --format \
    "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" \
    $(docker compose ps -q) 2>/dev/null || true
}

# ── Full teardown ─────────────────────────────────────────────────────────────
destroy() {
  warn "This will REMOVE all containers AND volumes (data will be lost)."
  read -r -p "  Type 'yes' to confirm: " CONFIRM
  [[ "$CONFIRM" == "yes" ]] || { info "Aborted."; exit 0; }
  $COMPOSE down --volumes --remove-orphans
  success "Stack and volumes destroyed"
}

# ── Full first-run setup ──────────────────────────────────────────────────────
setup() {
  banner
  check_prereqs
  setup_env
  build
  start
  pull_model
  init_qdrant
  echo ""
  echo -e "${GREEN}${BOLD}════════════════════════════════════════${RESET}"
  echo -e "${GREEN}${BOLD}  DataVault is ready!${RESET}"
  echo -e "${GREEN}${BOLD}════════════════════════════════════════${RESET}"
  echo ""
  echo -e "  Frontend  →  ${CYAN}https://localhost${RESET}"
  echo -e "  API Docs  →  ${CYAN}https://localhost/api/docs${RESET}"
  echo -e "  Qdrant UI →  ${CYAN}http://localhost:6333/dashboard${RESET}  (dev only)"
  echo -e "  Flower    →  ${CYAN}http://localhost:5555${RESET}            (dev only)"
  echo ""
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
CMD="${1:-help}"
shift || true

case "$CMD" in
  setup)         setup ;;
  build)         build "$@" ;;
  start|up)      start "$@" ;;
  stop|down)     stop "$@" ;;
  restart)       restart_svc "$@" ;;
  logs)          logs "$@" ;;
  status|ps)     status ;;
  pull-model)    pull_model ;;
  init-qdrant)   init_qdrant ;;
  destroy)       destroy ;;
  *)
    banner
    echo -e "${BOLD}Usage:${RESET} $0 <command>"
    echo ""
    echo "  setup          First-run: build, start, pull model, init Qdrant"
    echo "  build          Build all Docker images"
    echo "  start          Start all services"
    echo "  stop           Stop all services"
    echo "  restart <svc>  Restart a specific service"
    echo "  logs [svc]     Tail logs (all or specific service)"
    echo "  status         Show service status + resource usage"
    echo "  pull-model     Pull the configured Ollama LLM model"
    echo "  init-qdrant    Initialize Qdrant vector collections"
    echo "  destroy        Remove all containers and volumes"
    echo ""
    ;;
esac
