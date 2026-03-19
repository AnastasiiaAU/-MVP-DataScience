FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

COPY . .
RUN chmod +x /app/entrypoint.sh

# Для Telethon: .session файл должен быть доступен
VOLUME ["/app/sessions"]

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "main.py"]
