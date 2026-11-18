# Database Backup, Restore, and Migration Rollback

This procedure is for a dedicated PostFlowBot database only. Never point these commands at MY CASE or Mental Gaming production databases.

## Before any migration

1. Confirm the deployment is connected to the dedicated PostFlowBot database.
2. Pause schedulers and publishing workers so no writes are in flight.
3. Record the current Alembic revision with `alembic current`.
4. Take a database-native backup and verify that the backup file/object exists.
5. Test the backup restore into a separate disposable database before relying on it.

## SQLite

Stop the application first, then create a consistent backup using SQLite's backup command:

```sh
sqlite3 "$POSTFLOW_DATABASE_PATH" ".backup 'postflow-before-migration.sqlite3'"
```

Restore to a separate path for verification:

```sh
sqlite3 postflow-before-migration.sqlite3 ".restore 'postflow-restore-check.sqlite3'"
```

Do not overwrite the active database during a restore test.

## PostgreSQL

Use a custom-format dump and verify it can be listed:

```sh
pg_dump --format=custom --file=postflow-before-migration.dump "$POSTFLOW_DATABASE_URL"
pg_restore --list postflow-before-migration.dump
```

Restore into a newly created, isolated database (never directly over production) and run application schema checks.

## Migration and rollback

Apply migrations only after the backup is verified:

```sh
alembic upgrade head
alembic current
```

If the release must be rolled back, first pause all workers and assess whether the application has written data using the new schema. If a tested downgrade is safe:

```sh
alembic downgrade <PREVIOUS_REVISION>
```

Use the exact revision recorded before deployment. If downgrade would discard user data or is not known to be safe, restore the verified pre-migration backup into an isolated replacement database and switch the application only after validation.

## Post-restore checks

- Confirm the expected Alembic revision.
- Run the application's schema compatibility check.
- Verify row counts for critical tables such as admins, channels, contents, schedules, and publish jobs.
- Confirm foreign keys and unique constraints.
- Keep publishing disabled until an administrator verifies channel permissions and performs a controlled private-channel test.
- Record backup time, source revision, restore target, and verification outcome.

## Safety

- Never commit database URLs, credentials, dumps, SQLite files, Telegram tokens, or session files.
- Never run destructive restore or downgrade commands against MY CASE or Mental Gaming production systems.
- This repository's CI migrations use disposable SQLite databases; they are not a production migration rehearsal.
