#!/usr/bin/env sh
set -eu

mkdir -p "${SCREENSHOT_OUTPUT_DIR:-/app/data/screenshots}"
mkdir -p "$(dirname "${SQLITE_PATH:-/app/data/dreamlist.db}")"

celery -A app.celery_app:celery_app worker --loglevel=INFO &
CELERY_PID=$!

cleanup() {
  kill "$CELERY_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
