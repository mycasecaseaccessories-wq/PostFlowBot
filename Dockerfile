FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_SCHEMA_MODE=migrations \
    PUBLISHING_ENABLED=false \
    MEDIA_STORAGE_DIR=/app/data/media \
    TELEGRAM_SESSION=/app/data/telethon/postflow

WORKDIR /app

RUN groupadd --system postflow \
    && useradd --system --gid postflow --home-dir /app --shell /usr/sbin/nologin postflow

COPY requirements-prod.txt ./requirements-prod.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-prod.txt

COPY --chown=postflow:postflow . .

RUN mkdir -p /app/data/media /app/data/telethon \
    && chown -R postflow:postflow /app

USER postflow

CMD ["sh", "-c", "alembic upgrade head && exec python main.py"]
