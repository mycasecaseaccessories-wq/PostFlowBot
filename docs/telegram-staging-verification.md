# Telegram Staging Verification Runbook

## Purpose and safety boundary

Use this procedure only in a dedicated staging environment. It verifies the complete source-channel intake → publish-job → Telegram delivery → receipt path.

- Use a dedicated Telegram test user account and, preferably, a dedicated staging bot token.
- Create private staging source and destination channels with no public audience.
- Do not add production channels, production groups, customers, or public destinations to staging routes.
- Do not reuse a production Telethon session, bot token, database, or persistent data volume.
- Keep PUBLISHING_ENABLED=false until all preflight checks are complete.
- Never paste bot tokens, API hashes, phone codes, 2FA passwords, or Telethon session files into chat, tickets, logs, or source control.

A CI migration smoke test is not a Telegram staging test. Record actual Telegram message IDs and persisted receipt rows as evidence.

## Required isolated resources

1. A staging host or isolated local environment running the reviewed image.
2. A fresh SQLite database and a dedicated persistent data volume.
3. A dedicated Telegram test user account for the Telethon publisher/listener.
4. A private staging source channel and a private staging destination channel.
5. A staging admin bot configuration and an authorized operator Telegram user ID.

The Telethon test account must be able to read the source channel and post messages in the destination channel. Grant only the permissions required for this test.

## Configure the isolated environment

Set the required values in a protected environment file or secret manager on the staging host:

- BOT_TOKEN: staging bot token
- API_ID and API_HASH: Telegram application credentials
- ADMIN_USER_IDS: staging operator Telegram user ID(s)
- TELEGRAM_SESSION=/app/data/telethon/staging-postflow
- DATABASE_URL=sqlite+aiosqlite:////app/data/staging-postflow.db
- DATABASE_SCHEMA_MODE=migrations
- MEDIA_STORAGE_DIR=/app/data/media
- PUBLISHING_ENABLED=false

Ensure the staging database and /app/data volume are not shared with any other deployment. Restrict the environment file and session directory to the service account.

Create the Telethon session as a controlled one-time operation on the staging host using the repository's scripts/create_session.py procedure. Enter the phone code and 2FA password only in that trusted terminal. Confirm the resulting session file is stored in the staging volume and is not included in an image, log, backup shared outside the authorized team, or Git commit.

## Preflight — publishing must remain disabled

1. Confirm the active deployment, database path, session path, and bot token are staging-only.
2. Confirm both channels are private and their IDs/usernames are not production destinations.
3. Confirm the Telethon account can read the source and has post permission in the destination.
4. Confirm the staging operator is authorized for admin commands.
5. Start the application with PUBLISHING_ENABLED=false.
6. Check /status: database connected, Telethon connected and authorized.
7. Verify the configured source → destination route points only to the two private staging channels.
8. Check /publish_jobs and confirm there are no unexpected pending jobs.

Do not proceed if any destination, account, database, or route cannot be positively identified as staging-only.

## Controlled delivery test

Only after preflight passes, an authorized staging operator may enable publishing in the isolated staging environment. Do not change the production environment.

1. Set PUBLISHING_ENABLED=true in the staging environment only, then restart the staging service.
2. Verify /status and confirm the publishing worker starts in staging.
3. Post a unique, harmless text marker such as POSTFLOW-STAGING-TEXT-<UTC timestamp>-<random suffix> to the private source channel.
4. Confirm the corresponding destination message appears exactly once.
5. Inspect the job with /publish_jobs and /publish_job JOB_ID; record the successful attempt and destination message ID receipt.
6. Repeat with a harmless single-photo post and then a two-item album. Confirm the photo arrives, the album remains grouped, and every album message ID has an individual persisted receipt.
7. Confirm the job history, attempt state, receipt rows, and audit events agree with the messages visible in the destination.
8. Confirm completed jobs are not automatically resent. Do not manually retry a successful job.
9. If any send has an unknown outcome or is marked uncertain, do not retry until an operator has checked the destination and confirmed whether Telegram accepted the original send.

Use no customer data, copyrighted promotional content, or sensitive media in these tests.

## Evidence to record

Keep a staging test record with:

- test date/time (UTC), image tag/digest, and Git commit SHA;
- confirmation that the source and destination were private staging channels;
- redacted staging environment/configuration identifiers (never secret values);
- /status outcome before and during the test;
- test marker for each text/photo/album case;
- publish job IDs, attempt outcomes, and all returned Telegram message IDs;
- receipt-row count and audit-event verification;
- duplicate-delivery observation;
- any errors, uncertain outcomes, and operator action;
- final teardown confirmation.

Do not store session files, tokens, API hashes, OTPs, or 2FA credentials in the evidence record.

## Teardown

1. Set PUBLISHING_ENABLED=false in staging and restart the service.
2. Verify the publishing worker is stopped.
3. Remove test posts from the private staging destination if appropriate.
4. Remove temporary channel routes and revoke the test account's temporary channel permissions.
5. Securely retain or destroy the staging session and data according to the test environment's retention policy.
6. Confirm no staging credentials or data were copied into production.
7. Mark the Phase 4 staging gate complete only after the evidence above has been reviewed.

## Pass criteria

- Text, single-photo, and album posts each reach the private staging destination exactly as expected.
- Every delivery has a successful job/attempt record and matching persisted Telegram message ID receipt(s).
- Album receipts cover every message returned by Telegram.
- No duplicate send occurs during normal completion.
- An ambiguous delivery remains uncertain and is not automatically resent.
- Teardown leaves publishing disabled.

A passing staging test does not authorize production deployment or production publishing. Production release requires a separate explicit approval after target-host backup/restore, persistence, restart, migration, and security checks are complete.
