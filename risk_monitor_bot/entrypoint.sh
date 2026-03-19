#!/bin/sh
set -e
# Миграции перед стартом приложения (ожидаем готовность Postgres через depends_on)
python -m alembic upgrade head
exec "$@"
