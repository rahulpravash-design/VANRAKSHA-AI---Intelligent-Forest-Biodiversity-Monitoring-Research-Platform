#!/bin/sh
# Runs migrations before the API starts — alembic upgrade head is idempotent
# (a no-op once the database is already at head), so this is safe on every
# container start/restart, not just the first one.
set -e

alembic upgrade head
# Managed hosts (Render, Railway, Fly, Cloud Run) assign the port to bind and
# pass it in as $PORT; compose publishes 8000 and sets nothing.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
