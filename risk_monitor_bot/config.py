from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram Bot
    BOT_TOKEN: str

    # Telethon (для парсинга каналов)
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    TELEGRAM_PHONE: str

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/risk_monitor"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Parsing
    TELEGRAM_CHANNELS: list[str] = [
        "https://t.me/rbc_news",
        "https://t.me/novosty_trendy",
        "https://t.me/moscowmap",
        "https://t.me/rian_ru",
        "https://t.me/hiaimedia",
        "https://t.me/ostorozhno_novosti",
        "https://t.me/novosti_efir",
        "https://t.me/mash",
        "https://t.me/banksta",
        "https://t.me/stratmarketing",
        "https://t.me/productradar_official",
        "https://t.me/Salesnotes",
        "https://t.me/ecotopor",
        "https://t.me/ekonomika_banki",
        "https://t.me/prostoecon",
        "https://t.me/fat_cats_ru",
        "https://t.me/agronomika_news",
        "https://t.me/filatoff_inc",
        "https://t.me/business_slivki",
        "https://t.me/techno_yandex",
        "https://t.me/seeallochnaya",
        "https://t.me/ai_newz",
        "https://t.me/llm_under_hood",
        "https://t.me/ai_machinelearning_big_data",
        "https://t.me/techsparks",
        "https://t.me/habr_com",
        "https://t.me/TochkiNadAI",
        "https://t.me/neuraldvig",
        "https://t.me/okkaminsights",
        "https://t.me/decenter",
        "https://t.me/+SODl9OQMogFjYzM6",
        "https://t.me/government_rus",
        "https://t.me/kommersant",
        "https://t.me/retail_ru",
        "https://t.me/minstroyrf",
        "https://t.me/minpromtorg_ru",
        "https://t.me/MoscowExchangeOfficial",
    ]
    PARSE_INTERVAL_MINUTES: int = 15
    PARSE_MESSAGE_LIMIT: int = 50

    # Risk thresholds
    HIGH_RISK_THRESHOLD: float = 0.8
    MEDIUM_RISK_THRESHOLD: float = 0.5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("TELEGRAM_CHANNELS", mode="before")
    @classmethod
    def parse_telegram_channels(cls, value):
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                return value
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
