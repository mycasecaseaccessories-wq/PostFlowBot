"""Independent content processing interfaces for future phases."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProcessedContent:
    text: str | None
    media: Any = None


class ContentCleaner(ABC):
    @abstractmethod
    async def clean(self, content: ProcessedContent, **options: Any) -> ProcessedContent:
        raise NotImplementedError


class DuplicateChecker(ABC):
    @abstractmethod
    async def already_processed(
        self, source_channel_id: int, target_channel_id: int, source_message_id: int
    ) -> bool:
        raise NotImplementedError


class ContentProcessor(ABC):
    @abstractmethod
    async def process(self, content: ProcessedContent, **options: Any) -> ProcessedContent:
        raise NotImplementedError