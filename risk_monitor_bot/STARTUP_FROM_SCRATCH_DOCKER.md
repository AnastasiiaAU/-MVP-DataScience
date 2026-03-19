# Запуск проекта с нуля (Docker)

Документ рассчитан на ситуацию: вы только что **клонировали репозиторий** и хотите запустить проект `Risk Monitor Bot`.

## Требования

1. Установлен **Docker Desktop** (или Docker Engine) и команда `docker compose` (v2).
2. Рабочий `.env` файл с токенами.
3. Для парсинга Telegram через **Telethon** нужна сессия пользователя:
   - файл `risk_monitor_bot/sessions/parser_session.session`

## Шаг 1. Перейдите в папку проекта

```bash
cd /Users/malixds/dev/mvp/-MVP-DataScience/risk_monitor_bot
```

## Шаг 2. Создайте `.env`

```bash
cp .env.example .env
```

Откройте `.env` и заполните обязательно:
- `BOT_TOKEN`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_PHONE`
- `OPENAI_API_KEY`

Остальные переменные можно оставить по умолчанию.

## Шаг 3. Один раз сделайте Telethon `first_auth`

Это интерактивный шаг: Telethon спросит код из Telegram.

Рекомендуемый способ (локально):

```bash
# 1) Создайте/активируйте виртуальное окружение (пример под macOS)
python3 -m venv .venv
source .venv/bin/activate

# 2) Поставьте зависимости
pip install -e .

# 3) Авторизуйтесь и создайте сессию
python scripts/first_auth.py
```

После успешного запуска в папке `sessions/` должен появиться файл:
- `sessions/parser_session.session`

> Если у вас в системе другой Python (или проблемы с зависимостями), скажите — подскажу как обойти.

## Шаг 4. Запустите проект (всё автоматически)

В репозитории есть скрипт, который:
- поднимает `postgres` и `redis`
- применяет миграции
- один раз заполняет `telegram_sources` (скрипт `init_channels.py`)
- запускает `bot`, `celery-worker`, `celery-beat`, `flower`
- для демонстрации запускает парсинг/обработку/уведомления вручную один раз

Запуск:

```bash
bash ./run_all_docker.sh
```

## Шаг 5. Что проверить после старта

1) **Flower** (наблюдение за задачами Celery):
- http://localhost:5555

2) **Telegram-бот**:
- отправьте в Telegram команду `/start`
- затем команду `/risks` (если есть подходящие/обработанные риски)

3) **PostgreSQL** (данные проекта):
- host: `localhost`
- port: `5433` (в compose проброшен наружу)
- database: `risk_monitor`
- user: `risk_user`
- password: значение `POSTGRES_PASSWORD` из `.env`

Таблицы, которые должны наполняться по мере работы:
- `telegram_sources` (после `init_channels.py`)
- `articles` (после парсинга)
- `summaries` и `risk_assessments` (после обработки)
- `notifications` (после отправки уведомлений)

## Важно про OpenAI

Если в логах worker вы видите `429 insufficient_quota`, значит на аккаунте OpenAI закончилась квота/доступ к оплате.
Тогда `summaries` и `risk_assessments` не появятся до пополнения квоты.

