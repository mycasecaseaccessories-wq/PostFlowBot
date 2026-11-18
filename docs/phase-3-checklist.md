# Phase 3 checklist — Content & Media Processing

## Telegram media intake
- [x] Detect photo and document-backed media in Telethon messages.
- [x] Preserve Telegram reusable file IDs and unique media identifiers.
- [x] Persist media type, filename, MIME type, size, dimensions, and duration.
- [x] Associate media with CMS content using ordered ContentMedia links.
- [x] Group messages sharing Telegram grouped_id into one album content record.
- [x] Preserve album caption and avoid creating one publish job per album item.
- [x] Download media bytes and atomically persist them under a configured persistent filesystem volume.\n- [x] Persist storage backend/key, SHA-256 checksum, byte size, retry status, and attempt count in the CMS.\n- [ ] Add an S3-compatible object-storage adapter and retention/garbage-collection policy.
- [x] Retry pending media downloads on listener startup by re-fetching the original source message.\n- [ ] Add scheduled retry/backoff and operator visibility for permanently inaccessible source media.
- [ ] Add album completion/debounce guarantees for slow or unusually large groups.\n- [ ] Track every individual source message ID in an album so edits/deletions of non-first items can be reconciled.

## Route-specific text processing
- [x] Implement deterministic username, URL, and keyword removal utility.
- [x] Build immutable per-target publish payloads with the configured route transformations.
- [ ] Add admin commands/UI to configure and preview route filters.
- [ ] Define whether original captions and formatted entities should be preserved after transformations.

## Safety and verification
- [ ] Run credential-free test suite and migration checks.
- [ ] Add mocked Telethon listener tests for photos, videos, documents, audio/voice, and albums.
- [ ] Perform staging-only media round-trip tests before enabling a publisher.
- [ ] Keep live posting and production deployment disabled.

## Storage note
The current implementation persists Telegram's reusable file ID plus media metadata and CMS associations. It does not download binary media into local disk or object storage yet. This avoids pretending that an ephemeral application filesystem is durable; object-storage configuration and lifecycle are a separately verified follow-up item.
