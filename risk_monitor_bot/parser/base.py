from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class RawMessage:
    source_id: int
    message_id: int
    text: str
    url: str
    published_at: datetime


class BaseParser(ABC):
    @abstractmethod
    async def fetch_new_messages(
        self,
        source_id: int,
        channel: str,
        last_message_id: int,
    ) -> list[RawMessage]:
        """Забрать новые сообщения из источника начиная с last_message_id."""
        raise NotImplementedError
