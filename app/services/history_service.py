"""History-service dependency boundary for future repost history views."""

from __future__ import annotations

from typing import Any


class HistoryService:
    async def list_history(self, **kwargs: Any) -> list[Any]:
        raise NotImplementedError("History management is not implemented in Phase 0.")