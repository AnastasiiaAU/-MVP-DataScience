# Командный проект в рамках курса "Быстрое создание MVP в DataScience". 

## Команда №3: 
Альяных Анастасия, Антипов Захар, Классен Анастасия, Ли Максим, Молчанова Мария, Петрухина Кристина


# Risk Monitor Bot


Telegram-бот для мониторинга бизнес-рисков на основе новостей из Telegram-каналов.

Проект собирает сообщения из источников, делает LLM-суммаризацию, оценивает риск для бизнеса,
сопоставляет событие с ОКВЭД и отправляет уведомления пользователям по их фильтрам.

## 1. Цели проекта

- Автоматизировать мониторинг внешней среды для бизнеса.
- Выделять только релевантные новости и превращать их в структурированные сигналы риска.
- Персонализировать оповещения по отрасли, региону и минимальному уровню риска.

## 2. Технологический стек

- Python 3.11+
- aiogram 3.x (бот)
- Telethon (user API Telegram для парсинга каналов)
- SQLAlchemy 2.0 async + asyncpg
- Alembic (миграции)
- Celery + Redis (фоновые задачи)
- OpenAI API (LLM-суммаризация и LLM-классификация)
- Docker / Docker Compose
- pytest + pytest-asyncio (тестирование)

## 3. Что реализовано

- Асинхронная доменная модель БД (`users`, `telegram_sources`, `articles`, `summaries`, `risk_assessments`, `notifications`).
- CRUD-слой с дедупликацией статей по SHA-256.
- Парсер Telegram-каналов через Telethon с обработкой `FloodWaitError`.
- FSM-онбординг в боте: отрасли -> регион -> порог риска.
- Команды бота `/start`, `/settings`, `/risks` + карточки риска с деталями.
- LLM-модуль суммаризации (`NewsSummarizer`) с JSON-ответом, retry и batch-режимом.
- LLM-модуль классификации (`RiskClassifier`) с confidence, ОКВЭД и объяснением.
- Celery-пайплайн:
  - `tasks.parsing.parse_all_channels`
  - `tasks.processing.process_articles_batch`
  - `tasks.notifications.send_pending_notifications`
- Контейнеризация (bot, worker, beat, flower, postgres, redis).
- Alembic-конфигурация для async SQLAlchemy + initial migration.
- Утилиты:
  - `scripts/first_auth.py` (первичная авторизация Telethon)
  - `scripts/init_channels.py` (начальная загрузка каналов в БД)
- Набор тестов: CRUD, parser, summarizer, classifier.

## 4. Архитектура и поток данных

1. Celery task `parse_all_channels` запускает `ParsingManager`.
2. `TelegramChannelParser` читает новые сообщения из активных источников (`telegram_sources`).
3. Сообщения сохраняются в `articles` (дедупликация по `hash`).
4. Celery task `process_articles_batch` берет `articles.is_processed = false`.
5. `NewsSummarizer` строит структурированную сводку (`summaries`).
6. `RiskClassifier` оценивает риск и формирует `risk_assessments`.
7. Celery task `send_pending_notifications` ищет неразосланные оценки риска.
8. Выбираются подходящие пользователи по ОКВЭД/региону/порогу.
9. Отправка Telegram-уведомлений и запись факта отправки в `notifications`.

## 5. Структура проекта

```text
risk_monitor_bot/
├── bot/
│   ├── handlers/               # start/settings/risks
│   ├── keyboards/              # inline/reply
│   ├── middlewares/            # DbSessionMiddleware
│   ├── states/                 # FSM состояния онбординга
│   └── notifications.py        # отправка алертов
├── parser/
│   ├── base.py                 # RawMessage + BaseParser
│   ├── telegram_parser.py      # Telethon parser
│   └── manager.py              # ParsingManager
├── ml/
│   ├── summarizer.py           # LLM summary -> structured JSON
│   ├── risk_classifier.py      # LLM risk classification
│   └── okved_extractor.py      # placeholder (v2)
├── db/
│   ├── models.py               # SQLAlchemy models
│   ├── engine.py               # async engine/session
│   ├── crud.py                 # data access functions
│   └── migrations/             # Alembic env + versions
├── tasks/
│   ├── celery_app.py
│   ├── parsing.py
│   ├── processing.py
│   └── notifications.py
├── scripts/
│   ├── first_auth.py
│   └── init_channels.py
├── tests/
├── main.py
├── config.py
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## 6. Спецификация БД

### `users`

- `id` (PK)
- `telegram_id` (unique, indexed)
- `username`
- `selected_okveds` (array/json)
- `selected_regions` (array/json)
- `risk_threshold` (`low`/`medium`/`high`)
- `is_active`
- `created_at`, `updated_at`

### `telegram_sources`

- `id` (PK)
- `channel_username` (unique)
- `channel_title`
- `channel_id`
- `is_active`
- `last_parsed_message_id`
- `created_at`

### `articles`

- `id` (PK)
- `source_id` -> `telegram_sources.id`
- `telegram_message_id`
- `text`
- `url`
- `published_at`
- `hash` (unique)
- `is_processed`
- `created_at`
- Unique constraint: `(source_id, telegram_message_id)`
- Индексы: `hash`, `is_processed`

### `summaries`

- `id` (PK)
- `article_id` -> `articles.id` (unique)
- `summary_text`
- `affected_industries`
- `affected_regions`
- `event_type`
- `tokens_used`
- `created_at`

### `risk_assessments`

- `id` (PK)
- `summary_id` -> `summaries.id` (unique)
- `risk_level`
- `confidence`
- `okved_codes`
- `explanation`
- `created_at`

### `notifications`

- `id` (PK)
- `user_id` -> `users.id`
- `risk_assessment_id` -> `risk_assessments.id`
- `sent_at`
- `is_read`

## 7. Спецификация Telegram-бота

### Команды

- `/start` — регистрация пользователя и запуск онбординга.
- `/settings` — просмотр и изменение фильтров.
- `/risks` — последние риски пользователя.

### FSM онбординг

1. `choosing_industry` — множественный выбор отраслей (toggle).
2. `choosing_region` — выбор федерального округа или всех регионов.
3. `choosing_threshold` — минимальный уровень риска.

Настройки сохраняются в `users.selected_okveds`, `users.selected_regions`, `users.risk_threshold`.

## 8. Спецификация парсинга Telegram

- Используется Telethon (user API), не Bot API.
- Сессия хранится в `sessions/parser_session.session`.
- В `fetch_new_messages(...)`:
  - `iter_messages(entity=..., min_id=..., limit=PARSE_MESSAGE_LIMIT)`
  - фильтр сообщений без текста
  - фильтр коротких сообщений (`len(text) < 50`)
  - обработка `FloodWaitError` с `asyncio.sleep(error.seconds)`
  - сортировка сообщений от старых к новым

## 9. Спецификация LLM-модулей

### `NewsSummarizer`

- Протокол: `chat.completions.create(..., response_format={"type": "json_object"})`
- Выход: `SummaryResult`
  - `summary_text`
  - `affected_industries`
  - `affected_regions`
  - `event_type`
  - `tokens_used`
- Retry на `RateLimitError` (tenacity, 3 попытки, exponential backoff).
- Обработка `NOT_RELEVANT`.
- `summarize_batch()` через `asyncio.gather` + semaphore (до 5 параллельно).

### `RiskClassifier`

- Протокол: JSON-ответ от LLM.
- Выход: `RiskResult`
  - `risk_level`
  - `confidence`
  - `okved_codes`
  - `explanation`
  - `tokens_used`
- Валидация `risk_level` в `low|medium|high`.
- Правило: `confidence < 0.3 => low`.
- Retry на `RateLimitError`.

## 10. Celery и расписание

`tasks/celery_app.py`:

- timezone: `Europe/Moscow`
- reliability:
  - `task_acks_late=True`
  - `task_track_started=True`
  - `worker_prefetch_multiplier=1`

Beat schedule:

- `parse-telegram-channels` — `tasks.parsing.parse_all_channels`, раз в `PARSE_INTERVAL_MINUTES`
- `process-unprocessed-articles` — `tasks.processing.process_articles_batch`, каждые 5 минут
- `send-notifications` — `tasks.notifications.send_pending_notifications`, каждые 3 минуты

## 11. Конфигурация

Все настройки описаны в `config.py` и `.env.example`.

Ключевые переменные:

- `BOT_TOKEN`
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`
- `DATABASE_URL`
- `REDIS_URL`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `TELEGRAM_CHANNELS`
- `PARSE_INTERVAL_MINUTES`, `PARSE_MESSAGE_LIMIT`
- `HIGH_RISK_THRESHOLD`, `MEDIUM_RISK_THRESHOLD`

## 12. Локальный запуск

1. Создать `.env`:

```bash
cp .env.example .env
```

2. Установить зависимости:

```bash
pip install -e .
```

3. Первичная авторизация Telethon (один раз, интерактивно):

```bash
python scripts/first_auth.py
```

4. Заполнить источники каналов:

```bash
python scripts/init_channels.py
# или
python scripts/init_channels.py @channel1 @channel2
```

5. Запуск бота:

```bash
python main.py
```

6. Запуск worker/beat (в отдельных процессах):

```bash
celery -A tasks.celery_app worker --loglevel=info --concurrency=2
celery -A tasks.celery_app beat --loglevel=info
```

## 13. Запуск в Docker

```bash
docker compose up --build
```

Сервисы:

- `postgres` — PostgreSQL 16
- `redis` — Redis 7
- `bot` — aiogram bot
- `celery-worker`
- `celery-beat`
- `flower` — мониторинг Celery на `http://localhost:5555`

Важно: директория `./sessions` монтируется в `/app/sessions` для Telethon session file.

## 14. Миграции Alembic

Файлы миграций расположены в `db/migrations`.

- Конфиг: `alembic.ini`
- Async env: `db/migrations/env.py`
- Начальная миграция: `db/migrations/versions/20260311_000001_initial_tables.py`

Примеры команд:

```bash
alembic upgrade head
alembic downgrade -1
```

или

```bash
python -m alembic upgrade head
```

## 15. Тесты

Добавлены тесты:

- `tests/test_crud.py`
- `tests/test_parser.py`
- `tests/test_summarizer.py`
- `tests/test_classifier.py`

Установка test-зависимостей:

```bash
pip install -e ".[test]"
```

Запуск:

```bash
pytest -v --asyncio-mode=auto
```

## 16. Ограничения текущей версии

- Для Telethon требуется реальный user-аккаунт Telegram и интерактивная первичная авторизация.
- Содержимое LLM-ответов зависит от модели и может требовать дополнительной валидации в production.
- В MVP извлечение ОКВЭД выполняется через LLM-классификатор; `OkvedExtractor` пока placeholder.

## 17. План развития (v2+)

- Расширение источников: web/RSS парсеры (например, TASS и другие не-Telegram источники).
- Продвинутый движок matching по ОКВЭД (справочник + embeddings/NER).
- Админ-панель для управления источниками и пользователями.
- Метрики, трассировка и алерты по качеству/ошибкам пайплайна.
- Более строгая идемпотентность отправки уведомлений и ретраи доставки.
