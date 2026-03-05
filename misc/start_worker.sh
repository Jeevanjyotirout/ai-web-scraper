#!/usr/bin/env bash
# Start the Celery worker with sensible defaults
set -euo pipefail

CONCURRENCY=${CELERY_CONCURRENCY:-4}
LOG_LEVEL=${CELERY_LOG_LEVEL:-INFO}

echo "Starting Celery worker (concurrency=${CONCURRENCY})"

exec celery -A app.workers.celery_app.celery_app worker \
  --loglevel="${LOG_LEVEL}" \
  --concurrency="${CONCURRENCY}" \
  --queues=scrape_jobs,export_jobs,default \
  --hostname=worker@%h \
  --without-gossip \
  --without-mingle
