# Phase 1 — Foundation Checklist

Status legend: [x] implemented and covered by repository tests; [ ] not yet implemented/verified; [!] requires owner-provided setup or external credential.

## Baseline audit
- [x] Async Python application entry point and lifecycle orchestration.
- [x] aiogram administrator bot and Telegram user-client integration boundary.
- [x] SQLAlchemy models for admins, source channels, target channels, routing rules, and repost history.
- [x] Alembic migration foundation and schema-adoption safeguards.
- [x] CMS persistence models for categories, collections, content, media, and tags.
- [x] APScheduler lifecycle boundary.
- [x] Secret-safe configuration validation and logging foundation.
- [x] Add GitHub Actions test workflow for Python tests.

## Phase 1 implementation
- [x] Add an explicit workspace/role model for dashboard and bot access.
- [x] Add content approval persistence model.
- [x] Add schedule, publish job, and publish attempt persistence models.
- [x] Add idempotency constraints and indexes for due-job claiming.
- [x] Add an atomic due-job claim primitive that conditionally transitions one queued job to processing.
- [x] Test that the same due job cannot be claimed twice sequentially.
- [x] Define target-channel posting permission state, last-checked timestamp, and error detail.
- [x] Define content intake origin: manual, AI-assisted, and authorized channel import.
- [x] Prevent duplicate imported messages with a source-channel/message uniqueness constraint.
- [x] Add Phase 1 model tests and extend migration-head assertions.
- [x] Make the additive channel/content migration compatible with SQLite and PostgreSQL using Alembic batch operations.
- [x] Document backup, restore, and migration rollback procedure.
- [x] Verify the latest full CI run passes after the SQLite migration fix (GitHub Actions Run #46, job `test`, conclusion `success`, associated with commit `f34ca53b937b9f4de86fead4ec54c38d09d9b1a0`).
- [x] Implement an injectable supervised queue worker with continuous polling and graceful stop-event handling.
- [x] Persist successful Telegram message IDs and publish-attempt outcomes.
- [x] Retry only failures explicitly confirmed as not delivered, using bounded exponential backoff.
- [x] Move ambiguous network outcomes to an UNCERTAIN state; never automatically resend them.
- [x] Add operator-audited recovery for uncertain jobs and stale processing locks.
- [x] Block delivery unless the target channel posting permission is verified.
- [x] Add worker tests for success, retry, uncertain delivery, stale-lock recovery, and permission gating.
- [x] Verify migration upgrade/downgrade round trips and preserve Phase 0 admin data in disposable SQLite databases.
- [x] Verify latest worker implementation with GitHub Actions CI (Runs #67 and #68, both successful).


## External setup required before live Telegram integration
- [!] Create a dedicated Telegram bot with @BotFather and configure its token as a server-side secret.
- [!] Add the bot as an administrator to each target channel with permission to post.
- [!] If channel intake from private/restricted channels is required, configure an authorized Telegram user session separately; do not send OTPs or session files in chat.
- [!] Choose a private test channel for end-to-end publishing tests.
- [!] Configure a dedicated database and hosting environment. Existing MY CASE and Mental Gaming production databases must remain untouched.

## Acceptance criteria
- Existing tests pass without live Telegram credentials.
- Migrations apply and roll back on a disposable test database without data loss.
- Every target channel has an explicit permission status.
- Duplicate source-channel messages cannot create duplicate imported content.
- Publish jobs have a unique idempotency key.
- No post is sent to a target until an administrator explicitly enables that target and the publishing feature.

## Verification record
- Previous baseline CI: Run #48 (`44257412695`) — Python CI / `test` job completed successfully before the worker implementation.
- Latest verified worker implementation commit: `cfb36be7cab16ad8cc57c0f12e4f3c283f74f240`. GitHub Actions Run #67 (`44261924134`, push) and Run #68 (`44261930171`, pull_request) both completed successfully.
- Pull request: https://github.com/mycasecaseaccessories-wq/PostFlowBot/pull/1
- Previous CI run: 43910019000 — 35 passed, 4 migration tests failed because SQLite does not support direct ALTER TABLE constraint creation.
- Migration fix commit: 6ef9e01008c45aea8d216c5d40483b1205257d3c
- Current CI status: latest worker implementation is green in both push and pull-request CI runs.
- Verification environment: GitHub Actions, Python 3.11, SQLite test databases.
- No production database migration or Telegram publishing was run.


## Deferred to later Telegram integration and publishing phases
- [ ] Connect the worker to the real Telegram Bot API publisher and application lifecycle.
- [ ] Implement full media/album publishing and source-channel intake.
- [ ] Configure private staging bot/channel credentials and run live end-to-end Telegram delivery.
- [ ] Hosting, production secrets, and production deployment remain deferred until all six development phases are complete.
