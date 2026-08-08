# PostFlow Bot

Phase 0 foundation for an async Telegram channel monitoring and reposting system.

## Run & Operate

- `uv run pytest -q` — run the Phase 0 test suite
- `uv run python main.py` — run the service after configuring `.env`
- `uv run python scripts/create_session.py` — create a Telethon session interactively, once
- `python -m compileall -q app main.py tests` — syntax check
- Required environment variables are documented in `.env.example`

## Stack

- Python 3.11+
- Telethon for the authorized user client
- aiogram 3.x for the admin bot
- SQLAlchemy 2.x async ORM with SQLite in Phase 0
- APScheduler initialized for future scheduling work
- python-dotenv for environment loading
- pytest and pytest-asyncio for tests

## Where things live

- `app/config` — validated environment settings
- `app/database` — async engine, models, and repositories
- `app/bot` — admin authentication middleware and aiogram handlers
- `app/telegram` — Telethon client, listener, and publisher abstraction
- `app/services` — business-service boundaries reserved for future phases
- `app/core` — lifecycle, status, logging, and shared exceptions
- `tests` — credential-free configuration, auth, and database tests
- `main.py` — application entry point

## Architecture decisions

- The Telethon user client and Telegram admin bot are separate components with separate responsibilities.
- All startup dependencies are created by `Application`; the Telethon client has one owner and is injected into the listener.
- SQLAlchemy URLs are used instead of SQLite-specific APIs so PostgreSQL can replace SQLite later.
- Phase 0 listener and publisher interfaces are intentionally inert: receiving an event never publishes it.
- The database uniqueness constraint prevents the same source message being processed twice for one source/target relationship.

## Product

The foundation validates configuration, initializes persistence, authenticates admin Telegram users,
reports health, and prepares safe extension points for monitoring, processing, duplicate checks, and
publishing. Automatic reposting is intentionally deferred.

## User preferences

- Keep Phase 0 limited to foundation work; do not start Phase 1 automatically.

## Gotchas

- The production entry point never prompts for a phone number, OTP, or password.
- Run `scripts/create_session.py` once for interactive Telethon authorization before production startup.
- `.env`, Telethon session files, and local database data are ignored by Git.
- Without live Telegram credentials, tests still run because Telegram network calls are not required by the suite.

## Pointers

- See `.env.example` for the complete configuration surface.
- See `README.md` for setup, architecture, troubleshooting, and Phase 0 limitations.
