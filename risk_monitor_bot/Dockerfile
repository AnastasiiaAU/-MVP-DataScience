FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

COPY . .

# Для Telethon: .session файл должен быть доступен
VOLUME ["/app/sessions"]

CMD ["python", "main.py"]
