#!/bin/sh
# Runs migrations before the API starts — alembic upgrade head is idempotent
# (a no-op once the database is already at head), so this is safe on every
# container start/restart, not just the first one.
set -e

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
