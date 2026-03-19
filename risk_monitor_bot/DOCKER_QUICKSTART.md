# Запуск проекта через Docker с нуля

После клонирования репозитория выполните шаги по порядку.

## 1. Перейти в папку проекта

```bash
cd risk_monitor_bot
```

## 2. Создать файл настроек

```bash
cp .env.example .env
```

Откройте `.env` и **обязательно** заполните:

| Переменная | Где взять |
|------------|-----------|
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) в Telegram — создайте бота, скопируйте токен |
| `TELEGRAM_API_ID` | [my.telegram.org](https://my.telegram.org) — зайдите под своим номером, создайте приложение |
| `TELEGRAM_API_HASH` | то же приложение на my.telegram.org |
| `TELEGRAM_PHONE` | ваш номер в формате +79991234567 |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) — ключ API OpenAI |

Остальные переменные (БД, Redis, каналы) можно оставить по умолчанию.

## 3. Один раз: авторизация Telethon (локально)

Парсер каналов работает от пользовательского аккаунта Telegram. Нужно один раз создать сессию **на вашем компьютере** (интерактивно вводится код из Telegram):

```bash
pip install -e .
python scripts/first_auth.py
```

Введите код из Telegram, когда попросит. В папке `sessions/` появится файл `parser_session.session` — он будет подмонтирован в контейнеры.

> Если не хотите ставить зависимости локально: после первого `docker compose up --build` зайдите в контейнер и выполните `first_auth` там (сложнее, нужен интерактивный ввод в контейнер).

## 4. Загрузить каналы в БД (обязательно для работы парсера)

**Без этого шага таблицы так и останутся пустыми:** парсер берёт список каналов из таблицы `telegram_sources`, а не из `.env`. Один раз выполните:

```bash
docker compose run --rm bot python scripts/init_channels.py
```

Список каналов берётся из `.env` (`TELEGRAM_CHANNELS`). Можно передать свои:  
`docker compose run --rm bot python scripts/init_channels.py @channel1 @channel2`

После выполнения в БД появятся строки в `telegram_sources`. Дальше задачи Celery смогут парсить каналы и заполнять `articles` и остальные таблицы.

## 5. Запустить всё через Docker Compose

```bash
docker compose up --build
```

Будут запущены:

- **postgres** — БД (порт 5432)
- **redis** — очереди (порт 6379)
- **bot** — Telegram-бот (при старте автоматически выполняются миграции Alembic)
- **celery-worker** — фоновые задачи (парсинг, обработка, уведомления)
- **celery-beat** — расписание задач
- **flower** — мониторинг Celery: http://localhost:5555

Бот будет отвечать в Telegram на команды `/start`, `/settings`, `/risks`.

---

## Демонстрация работы

### 1. Регистрация в боте

В Telegram найдите своего бота (по username из BotFather) и отправьте **`/start`**. Пройдите онбординг: выберите отрасли, регион и минимальный уровень риска. После этого вы попадёте в таблицу `users`, и бот сможет присылать вам уведомления.

### 2. Запуск пайплайна (чтобы не ждать расписания)

По умолчанию парсинг каналов — раз в 15 минут, обработка статей — каждые 5 минут. Чтобы **сразу** подтянуть новости и обработать их (удобно для демо), выполните вручную:

```bash
# Собрать новые посты из каналов в articles
docker compose run --rm bot celery -A tasks.celery_app call tasks.parsing.parse_all_channels

# Обработать необработанные статьи (суммаризация + оценка риска)
docker compose run --rm bot celery -A tasks.celery_app call tasks.processing.process_articles_batch

# Разослать накопленные уведомления пользователям
docker compose run --rm bot celery -A tasks.celery_app call tasks.notifications.send_pending_notifications
```

Либо подождите 15–20 минут — beat сам запустит эти задачи по расписанию.

### 3. Где смотреть результат

| Что показать | Где |
|--------------|-----|
| **Задачи Celery** (парсинг, обработка, очереди) | http://localhost:5555 (Flower) |
| **Риски в боте** | В Telegram: команда **`/risks`** — список последних рисков по вашим фильтрам |
| **Настройки пользователя** | В Telegram: **`/settings`** |
| **Сырые данные** (каналы, статьи, сводки, оценки рисков) | DataGrip / любой клиент к PostgreSQL (порт **5433**, БД `risk_monitor`, пользователь `risk_user`) |

Таблицы: `telegram_sources` (каналы), `articles` (посты), `summaries` (сводки от LLM), `risk_assessments` (уровень риска, ОКВЭД), `notifications` (кому что отправлено).

---

## Остановка

```bash
docker compose down
```

Данные БД сохраняются в Docker volume `pgdata`. Чтобы удалить и их:

```bash
docker compose down -v
```
