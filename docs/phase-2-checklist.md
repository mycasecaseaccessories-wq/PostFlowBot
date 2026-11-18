# Phase 2 checklist

## Channel management
- [x] Reuse the existing SourceChannel and TargetChannel persistence/services.
- [x] Add/list/disable/enable source channels through Telegram admin commands.
- [x] Add/list/disable/enable target channels through Telegram admin commands.
- [x] Add/list/disable/enable source-to-target routes.
- [x] Reject self-routing and prevent duplicate source-target route pairs.

## Permission verification
- [x] Verify the connected Telethon account's channel participant/admin rights.
- [x] Persist verified/denied status, check timestamp, and error detail.
- [x] Require a fresh permission check when a target is re-enabled or re-added.
- [x] Queue intake only for active targets with verified posting permission.
- [x] Worker refuses to send to inactive targets or archived source content.

## Listener and intake
- [x] Wire NewMessage, MessageEdited, and MessageDeleted listeners into application lifecycle.
- [x] Import text messages into CMS with source channel/message origin.
- [x] Fan out one durable publish job per active source-to-target route.
- [x] Use database uniqueness and stable idempotency keys to prevent duplicate intake/jobs.
- [x] Synchronize edits to imported text/captions without creating duplicate jobs.
- [x] Archive deleted source messages and cancel their still-queued publish jobs.
- [ ] Media-only posts, albums, and media file persistence (deferred to media publishing phase).

## Deferred integration boundary
- [ ] Live Telegram publishing adapter and worker lifecycle integration.
- [ ] Live staging verification with a real Telegram account.

## Safety
The listener currently imports text-only messages. Media-only messages and albums are deliberately deferred rather than partially reposted. Queue jobs are persisted, but no live publisher is activated and no production deployment is performed. Re-enabling a target clears its permission status; run `/target_check TARGET_ID` again before enabling routes.
