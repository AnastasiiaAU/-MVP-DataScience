#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "== Risk Monitor Bot: Docker bootstrap =="

if [[ ! -f ".env" ]]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
fi

SESSION_FILE="$ROOT_DIR/sessions/parser_session.session"
if [[ ! -f "$SESSION_FILE" ]]; then
  echo "Telethon session not found: $SESSION_FILE"
  echo "1) Fill .env"
  echo "2) Run Telethon first auth locally:"
  echo "   python scripts/first_auth.py"
  exit 1
fi

echo "Starting postgres + redis..."
docker compose up -d postgres redis

echo "Waiting for postgres healthcheck..."
until docker compose exec -T postgres pg_isready -U risk_user -d risk_monitor >/dev/null 2>&1; do
  sleep 2
done

echo "Applying schema (init_channels will also create tables)..."
docker compose run --rm bot python scripts/init_channels.py

echo "Starting all services..."
docker compose up -d --build bot celery-worker celery-beat flower

echo "Warming up pipeline once (for demo):"
set +e
docker compose run --rm bot celery -A tasks.celery_app call tasks.parsing.parse_all_channels
docker compose run --rm bot celery -A tasks.celery_app call tasks.processing.process_articles_batch
docker compose run --rm bot celery -A tasks.celery_app call tasks.notifications.send_pending_notifications
set -e

echo ""
echo "Done."
echo "Flower: http://localhost:5555"
echo "Postgres: localhost:5433 (db=risk_monitor, user=risk_user)"
echo "Telegram: send /start then /risks"

