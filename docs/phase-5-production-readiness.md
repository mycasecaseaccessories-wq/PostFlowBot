# Phase 5 — Production Readiness & Final Audit

## Scope and release boundary

This phase hardens the deployable artifact and documents safe operations. It does not authorize production hosting, production Telegram publishing, or a production database migration. Telegram staging send/receipt verification remains a separate pending gate from Phase 4.

The application must remain configured with `PUBLISHING_ENABLED=false` until staging verification and the remaining release gates are explicitly completed.

## Container

The repository includes a Python 3.11 slim image that:

- installs runtime dependencies only (no pytest toolchain);
- runs as the unprivileged `postflow` user;
- keeps the SQLite database, Telethon session, and media under `/app/data`;
- defaults publishing to disabled;
- runs `alembic upgrade head` before application startup; and
- starts the existing graceful-shutdown-aware application process.

Build locally:

```bash
docker build -t postflow-bot:phase-5 .
```

Do not publish the image or deploy it as part of this phase. The image build requires no Telegram credentials. At runtime, supply secrets through the host's secret manager or a protected environment file; never bake them into build args, image layers, source control, or logs.

## Required runtime configuration

Set the following values in the runtime environment:

- `BOT_TOKEN`
- `API_ID`
- `API_HASH`
- `ADMIN_USER_IDS`
- `TELEGRAM_SESSION=/app/data/telethon/postflow`
- `DATABASE_URL=sqlite+aiosqlite:////app/data/postflow.db`
- `DATABASE_SCHEMA_MODE=migrations`
- `MEDIA_STORAGE_DIR=/app/data/media`
- `PUBLISHING_ENABLED=false`

Create the Telethon session as a separate, controlled one-time operation using the documented session setup procedure. Do not expose phone codes, 2FA passwords, session files, API hashes, or bot tokens to chat, logs, or build artifacts. Persist the complete `/app/data` directory on durable storage. Losing it can lose the SQLite database, downloaded media, and Telegram session state.

The current container configuration targets SQLite. A PostgreSQL deployment requires a compatible async PostgreSQL driver, a separately managed database, and dedicated integration testing; do not point this image at PostgreSQL until those are added and verified.

## Backup and recovery

Before every image upgrade or schema migration:

1. Stop the application so no worker is writing to the database or media store.
2. Take a SQLite-consistent backup of `postflow.db` using SQLite's backup API (for example, `sqlite3 data/postflow.db ".backup 'postflow-preupgrade.db'"`).
3. Back up the media directory and the Telethon session directory together with the database. Encrypt backups and restrict access because the session grants account access.
4. Record the current image tag and Alembic revision.
5. Verify backup integrity and periodically rehearse a restore into an isolated environment before relying on the backup.

Restore only while the application is stopped. Restore the database, media, and session from the same backup point, preserve restrictive file permissions, then start with publishing disabled and inspect `/status`, media state, and pending publish jobs. Never test recovery against production Telegram destinations.

Do not automatically downgrade a production database. If a migration fails, keep publishing disabled, preserve logs and the pre-migration backup, and investigate with a reviewed forward-fix or a rehearsed restore plan.

## Operational checks

After a future authorized deployment, verify:

- `/status` reports the expected bot, database, Telethon connection and authorization states;
- the configured admin Telegram IDs are correct and an unauthorized account cannot use admin commands;
- the service restarts cleanly and handles SIGTERM without abandoning active work;
- the data volume survives a container replacement;
- `/publish_jobs` and `/publish_job JOB_ID` expose queue/attempt/receipt state;
- stale-job recovery marks work uncertain and does not resend automatically;
- manual retry is used only after an operator verifies the destination has no existing delivery; and
- publishing remains disabled unless a separate release approval explicitly authorizes a staging-only test.

## Release gates

- [x] Runtime-only dependency manifest and non-root container definition added.
- [x] Container build context excludes credentials, local databases, sessions, and local application data.
- [x] Deployment, secret handling, persistent storage, backup, and recovery procedures documented.
- [ ] Build the image in CI and verify it starts with a disposable test database.
- [ ] Add and verify a durable backup/restore rehearsal in the target host.
- [ ] Complete authorized Telegram staging send/receipt verification (Phase 4 pending item).
- [ ] Complete target-host security, persistence, restart, and migration checks.
- [ ] Obtain explicit production release authorization.

## Current limitations

- No production host has been provisioned or configured.
- No image has been published to a registry.
- No live Telegram send has been performed as part of this phase.
- The container currently targets SQLite; PostgreSQL runtime support is not established by the schema abstraction alone.
- There is no HTTP health endpoint or container healthcheck in this release. Use process supervision and the Telegram admin `/status` command until a separately designed health interface is implemented.
