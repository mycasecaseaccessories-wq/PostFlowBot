# PostFlow Auto Posting Platform — System Blueprint

## Product scope

A private, multi-channel Telegram publishing workspace with two control surfaces:
- Responsive web dashboard for content creation, channel configuration, scheduling, and reporting.
- Telegram admin bot for quick commands, approvals, and operational alerts.

The platform supports three content intake paths:
1. Manual: admins write or upload text, photos, videos, documents, and albums.
2. AI-assisted: admins provide a topic, prompt, language, tone, and optional source facts; AI returns an editable draft. AI output is never published without an explicit approval setting.
3. Channel intake/reposting: monitor only source channels the account is authorized to access, apply configured transformations, then route eligible content to selected target channels. Respect Telegram permissions, source ownership, attribution settings, and content rights.

## Existing foundation

The current repository already contains the async aiogram admin bot, Telethon client boundary, channel/routing models, SQLAlchemy database layer, Alembic migrations, CMS persistence models, and a listener/scheduler lifecycle. These are retained and extended rather than replaced.

The existing publisher is intentionally a no-op and the CMS navigation is placeholder-only. No production publishing capability is claimed by this blueprint.

## High-level architecture

```text
Responsive Web Dashboard ─────┐
                              ├── Authenticated Application Services
Telegram Admin Bot ───────────┘              │
                                             ├── Content & Media Library
Manual Uploads ──────────────────────────────┤
AI Draft Provider ───────────────────────────┤
Authorized Source Channel Listener ─────────┤
                                             ├── Approval Workflow
                                             ├── Schedule & Durable Job Queue
                                             ├── Telegram Bot API Publisher
                                             ├── Retry / Idempotency / Audit Log
                                             └── Analytics & Notifications
```

## Core modules

### 1. Identity and access
- Allow-listed Telegram administrators remain supported.
- Web dashboard uses individual authenticated accounts and server-side authorization.
- Roles: Owner, Admin, Editor, Publisher, Viewer.
- Every mutation records actor, timestamp, and affected entity.
- Secrets are server-side only; never expose bot tokens, API hashes, AI keys, or database credentials to browser code.

### 2. Channel registry
- Manage multiple source and target channels.
- Store Telegram chat ID, display title, username, channel type, active state, and connection/permission status.
- Validate that the publishing bot is an administrator with permission to post before enabling a target.
- Support channel groups/workspaces and routing rules.
- Never assume a channel is writable merely because it is discoverable.

### 3. Content studio
- Draft, preview, edit, duplicate, archive, and delete content.
- Support text, photo, video, album, animation, audio, voice, document, and supported Telegram message types.
- Preserve captions, entities/formatting, buttons, and media ordering where supported.
- Media library deduplicates Telegram file IDs and stores metadata.
- Keep original imported content separate from transformed/published variants.

### 4. AI content assistant
- Provider-independent adapter so the model provider can be changed without rewriting publishing logic.
- Inputs: topic, facts, language, tone, length, CTA, target channel, and optional reference text.
- Outputs are drafts with provider/model metadata and generated-at timestamp.
- Require review/approval by default. Do not invent product prices, links, guarantees, or facts.
- Keep AI credentials in server-side environment variables.

### 5. Intake and repost rules
- Source channel monitoring is limited to channels the connected Telegram account is authorized to access.
- Rules can map one source to multiple targets, filter by keyword/media type, add/remove configured text, and set delays.
- Provide preview-before-enable and a pause switch per rule.
- Avoid duplicate processing with a unique source-message/rule key.
- Support edit/delete event policies as explicit settings; default to not silently rewriting or deleting already-published target posts.

### 6. Scheduler and publishing engine
- Store scheduled timestamps in UTC and display them in each channel/workspace timezone.
- Durable jobs survive application restarts; do not rely on in-memory timers as the source of truth.
- Job states: queued, scheduled, processing, published, failed, cancelled.
- Idempotency key prevents duplicate sends on retries.
- Retry transient failures with bounded exponential backoff; permanent permission/format errors require admin action.
- Rate-limit per bot/channel and record Telegram message IDs.
- Support one-off and recurring schedules, queue ordering, pause/resume, and publish-now.
- Publish through Telegram Bot API for target channels; use Telethon only for authorized source listening where required.

### 7. Telegram admin bot
- /start, /help, /status
- /channels, /queue, /schedule, /pause, /resume
- Inline actions for approve, reject, publish now, reschedule, and view errors.
- Enforce admin authorization on every command and callback.
- Bot actions use the same service layer as the dashboard.

### 8. Web dashboard
- Overview: queued, scheduled, published, failed, active channels.
- Content: editor, media upload, preview, AI draft, approval.
- Calendar and queue: drag/reschedule, timezone-aware display, filters.
- Channels: add/verify/pause, source/target labels, routing rules.
- Library: categories, collections, tags, media.
- History: search, delivery status, error details, Telegram message link when available.
- Settings: admins, roles, timezone, AI provider, notification preferences.

### 9. Observability and recovery
- Structured logs with token/session redaction.
- Health checks for database, bot API, listener, scheduler, and worker.
- Delivery audit trail and actionable error messages.
- Backup/restore procedure before production database migrations.
- Metrics: publish success rate, failures, queue depth, latency, and channel activity.

## Data model additions to plan

Retain existing Admin, SourceChannel, TargetChannel, RepostRule, RepostHistory, Category, Collection, Content, Media, ContentMedia, and ContentTag. Add or extend:
- Workspace and WorkspaceMember
- ChannelGroup and ChannelGroupMember
- ContentRevision and ContentApproval
- Schedule and ScheduleTarget
- PublishJob / PublishAttempt
- PublishHistory (manual/AI/scheduled/repost source attribution)
- AiGeneration
- NotificationPreference
- AuditEvent

Use explicit foreign keys, indexes for queue/status/time lookups, UTC timestamps, and unique idempotency constraints. Migrations must be additive and tested against a disposable database before any real database is upgraded.

## Delivery phases

1. Foundation: confirm repository baseline, document architecture, define migrations and environment boundaries.
2. Channel operations: channel CRUD, permission verification, routing rules, safe listener filtering.
3. Content studio: draft CRUD, media upload/library, preview, approval.
4. Publishing: Bot API publisher, durable queue, schedule worker, retries, idempotency, history.
5. AI assistant: provider adapter, editable generation, approval gates, usage/error records.
6. Dashboard: responsive web UI connected to the same service layer.
7. Telegram controls: admin commands, inline approvals, notifications.
8. Hardening: tests, backups, observability, staging verification, production release.

## Security and production boundaries

- Do not reuse the MY CASE or Mental Gaming production databases.
- Do not commit .env files, bot tokens, API hashes, Telethon session files, or AI keys.
- Create a dedicated database and deployment configuration for this application before production use.
- Never deploy a publishing worker that can send messages until target channel permissions and a test channel have been verified.
- Production publishing remains disabled until an owner explicitly configures credentials and enables it.
