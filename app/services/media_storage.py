"""Atomic local media storage for persistent mounted volumes."""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


class MediaStorageError(RuntimeError):
    """Raised when a media object cannot be safely stored."""


class MediaTooLargeError(MediaStorageError):
    """Raised when media exceeds the configured storage size limit."""


@dataclass(frozen=True, slots=True)
class StoredMedia:
    backend: str
    key: str
    sha256: str
    size: int


class LocalMediaStorage:
    """Store media atomically under a configured persistent filesystem mount.

    The directory must be backed by a persistent disk/volume in hosted
    environments. This class intentionally does not pretend ephemeral disk is
    durable object storage.
    """

    backend = "local"

    def __init__(self, root: str | Path, *, max_bytes: int = 52_428_800) -> None:
        self.root = Path(root).expanduser().resolve()
        self.max_bytes = max(1, int(max_bytes))

    @staticmethod
    def _safe_suffix(filename: str | None) -> str:
        suffix = Path(filename or "").suffix.lower()
        return suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else ""

    def _store_sync(
        self, source: Path, media_id: str, filename: str | None,
    ) -> StoredMedia:
        if not source.is_file():
            raise MediaStorageError("Downloaded Telegram media file is missing.")
        size = source.stat().st_size
        if size <= 0:
            raise MediaStorageError("Downloaded Telegram media file is empty.")
        if size > self.max_bytes:
            raise MediaTooLargeError(
                f"Media exceeds configured limit ({size} > {self.max_bytes} bytes)."
            )
        suffix = self._safe_suffix(filename)
        key = f"{media_id[:2]}/{media_id}{suffix}"
        destination = (self.root / key).resolve()
        if self.root not in destination.parents:
            raise MediaStorageError("Unsafe media storage key.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        fd, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as target, source.open("rb") as input_file:
                while chunk := input_file.read(1024 * 1024):
                    digest.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary_name, destination)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return StoredMedia(self.backend, key, digest.hexdigest(), size)

    async def store_file(
        self, source_path: str | Path, media_id: str, filename: str | None = None,
    ) -> StoredMedia:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", media_id):
            raise MediaStorageError("Invalid media identifier.")
        return await asyncio.to_thread(
            self._store_sync, Path(source_path), media_id, filename
        )

    def resolve(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root not in candidate.parents:
            raise MediaStorageError("Unsafe media storage key.")
        return candidate
