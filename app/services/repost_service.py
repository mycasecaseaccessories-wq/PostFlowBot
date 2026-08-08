"""Future repost orchestration boundary; intentionally inactive in Phase 0."""

from __future__ import annotations


class RepostService:
    async def handle_incoming_message(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Automatic reposting is not implemented in Phase 0.")