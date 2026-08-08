# PostFlow Bot

Phase 0 is the foundation for a Telegram content reposting system. It establishes
the boundaries between an authorized Telegram user client, an administrator bot,
the database, and future content-processing services.

Automatic reposting is **not** implemented in this phase.

## Architecture

The system has two Telegram components:

1. **Telethon user client** — represents the authorized user account that will
   eventually monitor channels the account can access.
2. **Telegram admin bot** — provides the administrator-only control interface.

The application lifecycle is:

```text
environment → configuration validation → database → Telethon state
→ admin bot → event listener
```

The listener currently observes new, edited, and deleted message event types.
New-message events are logged only; no content is cleaned, forwarded, or
published.

## Requirements

- Python 3.11 or newer
- A Telegram bot token from BotFather
- Telegram API ID and API hash from <https://my.telegram.org>
- A Telegram user account for the Telethon session
- Telegram user IDs for the administrators

The test suite does not need real Telegram credentials.

## Installing dependencies

Using the included `uv` setup:

```bash
uv sync --extra test
```

Or using a normal virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Creating the Telegram bot

1. Open Telegram and start a chat with `@BotFather`.
2. Use `/newbot` and follow the prompts.
3. Copy the generated token into `BOT_TOKEN` in `.env`.
4. Do not commit `.env` or place the token in source code.

## Getting Telegram API credentials

1. Sign in at <https://my.telegram.org>.
2. Open **API development tools**.
3. Create an application if needed.
4. Copy the numeric `api_id` to `API_ID` and the `api_hash` to `API_HASH`.
5. Keep `API_HASH` private.

## Environment configuration

Copy the example file:

```bash
cp .env.example .env
```

Set these required variables:

```dotenv
BOT_TOKEN=your-bot-token
API_ID=123456
API_HASH=your-32-character-api-hash
TELEGRAM_SESSION=data/telethon/postflow
ADMIN_USER_IDS=123456789,987654321
```

Optional values:

```dotenv
DATABASE_URL=sqlite+aiosqlite:///./data/postflow.db
LOG_LEVEL=INFO
TIMEZONE=UTC
```

`ADMIN_USER_IDS` accepts one or more positive Telegram user IDs separated by
commas. Invalid or missing values stop startup with a safe, specific error.
Secret values are never included in configuration errors or normal logs.

## Creating the Telethon session

The normal production startup flow never prompts for a phone number, OTP, or
password. Create the session as a separate one-time setup step:

```bash
uv run python scripts/create_session.py
```

The command reads `API_ID`, `API_HASH`, and `TELEGRAM_SESSION` from `.env`.
Telethon will interactively request the phone number and verification code, and
may request the account's two-factor password. The resulting `.session` file is
private and is protected by `.gitignore`.

After the session is created, production startup checks whether it is
authorized. An unauthorized session is reported as a warning and in `/status`;
the application does not launch an unclear OTP traceback.

## Running the project

```bash
uv run python main.py
```

The service starts the database, checks the Telethon client, registers the
listener foundation, and starts the aiogram admin bot polling. Press `Ctrl+C`
or send `SIGTERM` for a graceful shutdown.

If configuration is not present, startup exits safely and identifies the
missing variable without printing secret values.

## Admin authentication

Every admin bot message and callback is checked against `ADMIN_USER_IDS`.

- Authorized users can access `/start`, `/status`, `/help`, and the foundation
  keyboard.
- Unauthorized users receive `Access denied.`.
- Unauthorized users never receive the admin keyboard or feature responses.

The database does not store bot tokens, API hashes, sessions, or other secrets.

## Admin bot commands

- `/start` — shows the system summary and admin keyboard.
- `/status` — shows bot, database, Telethon, authorization, and listener state.
- `/help` — lists available commands and explains Phase 0 limitations.

The Source Channels, Target Channels, Routing Rules, Settings, and History buttons currently
return:

> 🚧 This feature will be available in the next phase.

## Database

Phase 0 uses SQLAlchemy 2.x async support with SQLite:

- `Admin`
- `SourceChannel`
- `TargetChannel`
- `RepostRule`
- `RepostHistory`
- `SystemSetting`

The database directory is created automatically. Foreign-key relationships,
indexes, timestamps, and a unique constraint on
`source_channel_id + target_channel_id + source_message_id` are included.
That uniqueness strategy prevents duplicate processing of a source message for
the same source/target relationship.

The `DATABASE_URL` setting uses a SQLAlchemy URL, so a later PostgreSQL
migration can use a different async driver without changing service contracts.

## Project structure

```text
app/
├── bot/
│   ├── auth.py                 # admin access middleware
│   ├── bot.py                  # aiogram lifecycle
│   └── handlers.py             # /start, /status, /help, placeholders
├── config/
│   └── settings.py             # environment loading and validation
├── core/
│   ├── lifecycle.py            # startup, shutdown, SIGINT/SIGTERM
│   ├── logger.py               # centralized redacted logging
│   └── status.py               # safe health snapshot
├── database/
│   ├── database.py             # async SQLAlchemy engine
│   ├── models.py               # Phase 0 data model
│   └── repositories/           # database access boundaries
├── services/                   # future processing/service boundaries
└── telegram/
    ├── client.py               # single Telethon client owner
    ├── listener.py             # event listener foundation
    └── publisher.py            # no-op-by-design publisher boundary
scripts/
└── create_session.py           # one-time interactive Telethon setup
tests/
├── test_auth.py
├── test_config.py
└── test_database.py
main.py
```

## What Phase 0 implements

- Modular async application structure
- Environment loading and required-variable validation
- Safe logging with secret redaction
- Automatic SQLite database directory and schema initialization
- SQLAlchemy models, relationships, indexes, and duplicate-processing constraint
- Multiple-admin authentication middleware for aiogram
- `/start`, `/status`, and `/help`
- Foundation keyboard with explicit future-phase notices
- Single-owner Telethon client initialization and connection state detection
- New, edited, and deleted message listener registration
- Content processor, cleaner, duplicate checker, and publisher interfaces
- APScheduler initialization boundary without scheduled jobs
- Graceful startup and shutdown, including SIGINT and SIGTERM
- Credential-free tests for configuration, authentication, database creation, and uniqueness
- Setup and troubleshooting documentation

## What Phase 0 does not implement

- Automatic reposting or forwarding
- Username, attribution, link, or keyword removal
- Source or target channel CRUD
- Repost-rule CRUD
- History UI or history management
- Publishing text, photos, videos, documents, audio, or media groups
- Automatic phone, OTP, or password prompts during production startup
- Scheduling jobs
- PostgreSQL migrations

## Testing

Run:

```bash
uv run pytest -q
```

The suite uses mocks and temporary SQLite databases. It does not call Telegram
and does not require a live bot token, API ID, API hash, or Telethon session.

## Troubleshooting

### `Required environment variable ... is missing`

Copy `.env.example` to `.env` and fill in every required value. The variable
name in the error is safe to share; never share the value of a secret.

### Telethon says the session is unauthorized

Run `uv run python scripts/create_session.py` and complete the interactive
authorization. Confirm `TELEGRAM_SESSION` points to the same session name or
path used during setup.

### The admin bot does not respond

Confirm the bot token is correct, the bot has been started in Telegram, and
your numeric Telegram user ID appears in `ADMIN_USER_IDS`.

### Database errors

Check that the process can create the directory containing the SQLite file.
The default location is `data/postflow.db`. For a later PostgreSQL deployment,
replace `DATABASE_URL` with a compatible SQLAlchemy async URL.

## Future roadmap

Later phases can add channel management, rule management, content cleaning,
duplicate checking workflows, media-aware publishing, history views, and
scheduling. Those phases should build on the boundaries in this foundation
without moving Telegram API calls into handlers or putting business logic in
`main.py`.
