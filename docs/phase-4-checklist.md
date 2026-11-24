# Phase 4 checklist — Telegram Publisher & Worker Integration

## Publisher
- [x] Implement Telethon-backed text publishing.
- [x] Implement single-media publishing from verified local persistent storage.
- [x] Implement grouped media albums as one Telethon send_file call.
- [x] Return every Telegram message ID created by a text, single-media, or album send.
- [x] Persist every album message ID as an individual delivery receipt linked to its publish attempt.
- [x] Classify Telegram FloodWait responses as confirmed retryable failures.
- [x] Classify Telegram RPC rejections as permanent failures.
- [x] Treat transport timeouts/connection failures as uncertain; never auto-retry ambiguous sends.
- [x] Refuse publishing when the Telethon account is disconnected or unauthorized.
- [x] Refuse media that is missing or not in the configured local storage backend.

## Worker and lifecycle
- [x] Feed route-specific text and ordered media payloads into the publisher.
- [x] Keep existing verified-target permission gate, idempotency, attempt history, exponential backoff, and uncertain-delivery safeguards.
- [x] Wire the supervised worker into application startup and graceful shutdown.
- [x] Require explicit PUBLISHING_ENABLED=true; default remains false.
- [ ] Complete full staging Telegram send/receipt verification with an authorized test account.
- [x] Add admin commands to list jobs, inspect attempt/receipt history, recover stale processing locks, and manually retry failed/uncertain jobs with audit events.
- [x] Add migration-backed per-message receipt storage for albums.

## Staging procedure
Follow [Telegram Staging Verification Runbook](telegram-staging-verification.md). The runbook defines isolated resources, protected session setup, disabled-publishing preflight, controlled text/photo/album delivery, receipt evidence, and teardown.

## Safety
Production hosting and live posting remain disabled by default. Do not enable publishing against production channels until staging verification, operational recovery controls, and all remaining project phases are complete.
