# Phase 3 checklist — Content & Media Processing

## Telegram media intake
- [x] Detect photo and document-backed media in Telethon messages.
- [x] Preserve Telegram reusable file IDs and unique media identifiers.
- [x] Persist media type, filename, MIME type, size, dimensions, and duration.
- [x] Associate media with CMS content using ordered ContentMedia links.
- [x] Group messages sharing Telegram grouped_id into one album content record.
- [x] Preserve album caption and avoid creating one publish job per album item.
- [ ] Download media bytes into durable object storage with checksums and retention policy.
- [ ] Add retry/recovery for expired Telegram file references and inaccessible source media.
- [ ] Add album completion/debounce guarantees for slow or unusually large groups.

## Route-specific text processing
- [x] Implement deterministic username, URL, and keyword removal utility.
- [ ] Wire transformed content snapshots into each queued publish payload.
- [ ] Add admin commands/UI to configure and preview route filters.
- [ ] Define whether original captions and formatted entities should be preserved after transformations.

## Safety and verification
- [ ] Run credential-free test suite and migration checks.
- [ ] Add mocked Telethon listener tests for photos, videos, documents, and albums.
- [ ] Perform staging-only media round-trip tests before enabling a publisher.
- [ ] Keep live posting and production deployment disabled.

## Storage note
The current implementation persists Telegram's reusable file ID plus media metadata and CMS associations. It does not download binary media into local disk or object storage yet. This avoids pretending that an ephemeral application filesystem is durable; object-storage configuration and lifecycle are a separately verified follow-up item.
