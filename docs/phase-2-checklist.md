# Phase 2 checklist

## Channel management
- [x] Reuse the existing SourceChannel and TargetChannel persistence/services.
- [x] Add Telegram admin commands to add/list/disable source channels.
- [x] Add Telegram admin commands to add/list/disable target channels.
- [x] Add route create/list commands and reject self-routing/duplicate route pairs.

## Permission verification
- [x] Verify the connected Telethon account's channel participant/admin rights.
- [x] Persist verified/denied status, check timestamp, and error detail.
- [x] Queue intake only for active targets with verified posting permission.

## Listener and intake
- [x] Wire NewMessage listener into application lifecycle and intake service.
- [x] Import text messages into CMS with source channel/message origin.
- [x] Fan out one durable publish job per active source-to-target route.
- [x] Use database uniqueness and stable idempotency keys to prevent duplicate intake/jobs.
- [ ] Edited/deleted source message synchronization.
- [ ] Media-only posts, albums, and media file persistence.
- [ ] Live Telegram publishing adapter and worker lifecycle integration (later phase).
- [ ] Live staging verification with a real Telegram account.

## Safety
The listener currently imports text-only messages. Media and albums are deliberately deferred rather than partially reposted. The queue is populated, but no live publisher is activated and no production deployment is performed.
