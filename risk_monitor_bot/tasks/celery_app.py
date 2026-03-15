from celery import Celery
from celery.signals import worker_process_init
from celery.schedules import crontab

from config import settings


@worker_process_init.connect
def _dispose_db_pool_after_fork(**kwargs):
    """Сбросить пул соединений БД после fork воркера, иначе asyncpg даёт "another operation in progress"."""
    try:
        from db.engine import engine
        engine.dispose()
    except Exception:
        pass


app = Celery(
    "risk_monitor",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["tasks.parsing", "tasks.processing", "tasks.notifications"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

app.conf.beat_schedule = {
    "parse-telegram-channels": {
        "task": "tasks.parsing.parse_all_channels",
        "schedule": crontab(minute=f"*/{settings.PARSE_INTERVAL_MINUTES}"),
    },
    "process-unprocessed-articles": {
        "task": "tasks.processing.process_articles_batch",
        "schedule": crontab(minute="*/5"),
    },
    "send-notifications": {
        "task": "tasks.notifications.send_pending_notifications",
        "schedule": crontab(minute="*/3"),
    },
}

# Backward-compatible alias for old import paths.
celery_app = app
