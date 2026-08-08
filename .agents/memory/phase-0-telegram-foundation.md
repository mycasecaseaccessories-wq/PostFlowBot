---
name: Phase 0 Telegram foundation
description: Durable scope and credential-handling decisions for the Telegram reposting foundation.
---

Phase 0 keeps live Telegram access optional for development: tests and database initialization must work without Telegram credentials, while production startup validates configuration and reports disconnected or unauthorized Telethon state safely.

**Why:** The Telegram connector was not authorized, and the foundation must remain testable without a live bot or user session.

**How to apply:** Keep future phases behind the existing service interfaces; do not add automatic publishing or interactive OTP prompts to normal startup.