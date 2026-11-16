# Phase 1 — Foundation Checklist

Status legend: [x] verified in the current repository; [ ] planned; [!] requires owner-provided setup or external credential.

## Baseline audit
- [x] Async Python application entry point and lifecycle orchestration.
- [x] aiogram administrator bot and Telegram user-client integration boundary.
- [x] SQLAlchemy models for admins, source channels, target channels, routing rules, and repost history.
- [x] Alembic migration foundation and schema-adoption safeguards.
- [x] CMS persistence models for categories, collections, content, media, and tags.
- [x] APScheduler lifecycle boundary.
- [x] Secret-safe configuration validation and logging foundation.
- [x] Run the full test suite on the feature branch: GitHub Actions passed (38 tests).
- [x] Add GitHub Actions test workflow for Python tests.

## Phase 1 implementation
- [x] Add an explicit workspace/role model for dashboard and bot access.
- [x] Add content approval persistence model.
- [x] Add schedule, publish job, and publish attempt persistence models.
- [x] Add idempotency constraints and indexes for due-job claiming.
- [ ] Define channel permission verification state and last-checked timestamp.
- [ ] Define source intake mode: manual, AI-assisted, and authorized channel intake.
- [x] Add Phase 1 model tests and extend migration-head assertions.
- [ ] Document restore and migration rollback procedure.

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
- A scheduled publish can be claimed once only, even if a worker restarts or retries.
- No post is sent to a target until an administrator explicitly enables that target and the publishing feature.


## Verification record
- Pull request: https://github.com/mycasecaseaccessories-wq/PostFlowBot/pull/1
- Latest CI run: 43908202906
- Result: success — 38 passed in 29.61s
- Verification environment: GitHub Actions, Python 3.11, SQLite test databases
- No production database migration or Telegram publishing was run.
