"""Phase 0 cleaner dependency boundary."""

from __future__ import annotations

from typing import Any

from .content_processor import ContentCleaner, ProcessedContent


class FoundationContentCleaner(ContentCleaner):
    """Pass-through placeholder; username/link removal starts in a later phase."""

    async def clean(self, content: ProcessedContent, **options: Any) -> ProcessedContent:
        return content