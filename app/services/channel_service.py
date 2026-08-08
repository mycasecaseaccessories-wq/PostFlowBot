"""Channel-service dependency boundary for future admin CRUD."""

from __future__ import annotations

from typing import Any


class ChannelService:
    async def list_sources(self, **kwargs: Any) -> list[Any]:
        raise NotImplementedError("Channel management is not implemented in Phase 0.")

    async def list_targets(self, **kwargs: Any) -> list[Any]:
        raise NotImplementedError("Channel management is not implemented in Phase 0.")