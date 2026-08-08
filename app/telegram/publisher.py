"""Publisher abstraction reserved for a future reposting phase."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Publisher(ABC):
    """Defines the future publishing dependency without sending messages today."""

    @abstractmethod
    async def publish_text(self, destination: int, text: str, **kwargs: Any) -> int:
        raise NotImplementedError

    @abstractmethod
    async def publish_media(self, destination: int, media: Any, **kwargs: Any) -> int:
        raise NotImplementedError


class TelegramPublisher(Publisher):
    """Explicit Phase 0 guard: no automatic publication is implemented."""

    async def publish_text(self, destination: int, text: str, **kwargs: Any) -> int:
        raise NotImplementedError("Automatic publishing is not implemented in Phase 0.")

    async def publish_media(self, destination: int, media: Any, **kwargs: Any) -> int:
        raise NotImplementedError("Automatic publishing is not implemented in Phase 0.")