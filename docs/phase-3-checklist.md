# Phase 3 checklist — Content & Media Processing

## Telegram media intake
- [x] Detect photo and document-backed media in Telethon messages.
- [x] Preserve Telegram reusable file IDs and unique media identifiers.
- [x] Persist media type, filename, MIME type, size, dimensions, and duration.
- [x] Associate media with CMS content using ordered ContentMedia links.
- [x] Group messages sharing Telegram grouped_id into one album content record.
- [x] Preserve album caption and avoid creating one publish job per album item.
- [x] Download media bytes and atomically persist them under a configured persistent filesystem volume.
- [x] Persist storage backend/key, SHA-256 checksum, byte size, pending/stored/failed status, attempt count, and last error in the CMS.
- [ ] Add an S3-compatible object-storage adapter and retention/garbage-collection policy.
- [x] Retry pending media downloads on listener startup by re-fetching the original source message.
- [ ] Add scheduled retry/backoff and operator visibility for permanently inaccessible source media.
- [x] Reset queued album publication time when another album item arrives (5-second quiet window).
- [x] Track each album media item against its original Telegram message ID.
- [x] Reconcile edits/replacements/deletions for individual album items; archive only after the final media item is removed.

## Route-specific text processing
- [x] Implement deterministic username, URL, and keyword removal utility.
- [x] Build immutable per-target publish payloads with the configured route transformations.
- [x] Add admin commands to configure and preview route filters (`/route_filters`, `/route_preview`).
- [x] Preserve source caption entities in canonical CMS data; pass them through only when route transformations leave text unchanged.

## Safety and verification
- [x] Add credential-free tests for media intake, storage, retry, album reconciliation, route filters, and the latest Alembic schema revision.
- [x] Add mocked Telethon media descriptor tests for photos, videos, voice, and generic documents.
- [ ] Add full mocked listener event tests for new/edit/delete and album event variations.
- [ ] Perform staging-only media round-trip tests before enabling a publisher.
- [ ] Keep live posting and production deployment disabled.

## Storage note
The application downloads source media and stores bytes atomically under `MEDIA_STORAGE_DIR`, with SHA-256 and size recorded in the database. The default `./data/media` path is durable only when hosting mounts a persistent volume there. No cloud object-storage adapter is enabled yet. Transient download failures remain `pending` with an error and attempt count; the listener retries them at startup by fetching the original source message. Files exceeding the configured size limit are marked `failed` and are not retried automatically. Scheduled backoff/retry and an operator dashboard remain future work.
