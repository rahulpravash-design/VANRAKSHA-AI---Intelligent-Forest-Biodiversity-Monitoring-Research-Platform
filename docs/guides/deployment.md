# Deployment notes

This is a checklist of what changes between local development and a real
deployment — not a hosting-provider walkthrough, since that choice is yours.

## Before going to production

Read `Settings.warn_insecure()` in `backend/app/core/config.py` — it checks
several of the items below and logs on startup when `VANRAKSHA_ENV=production`,
but does **not** refuse to start. Treat every one of its warnings as
blocking.

- [ ] **`JWT_SECRET`** — a long, random value (`python -c "import secrets;
      print(secrets.token_urlsafe(48))"`), never the development default.
- [ ] **`DEBUG=false`**.
- [ ] **`CORS_ORIGINS`** — the real frontend origin(s) only, never `*`.
- [ ] **Administrator account** — run `python scripts/bootstrap_admin.py`
      against a freshly migrated, otherwise-empty database, with
      `BOOTSTRAP_ADMIN_PASSWORD` set to a real password. Do **not** run
      `scripts/seed.py` in production — it creates a demo catalogue, fake
      staff accounts and synthetic observations, meant for development and
      demos only.
- [ ] **`STORAGE_BACKEND=s3`** — media on the API server's local disk does
      not survive a redeploy and does not scale; point it at S3-compatible
      object storage (or a CDN in front of it) instead.
- [ ] **`DATABASE_URL`** — a managed PostgreSQL instance with PostGIS
      installed; apply `database/postgis/001_spatial.sql` if you want the
      native spatial columns (optional — the app works without them).
- [ ] **Rate limiting** — `app/core/rate_limit.py` is in-process. Behind more
      than one worker or replica, the limit becomes per-worker; move it to a
      shared store (Redis) before scaling out the API.
- [ ] **Backups** — the database is the system of record; media in object
      storage should be backed up or versioned separately.
- [ ] **AI weights** — `AI_VISION_WEIGHTS` / `AI_AUDIO_WEIGHTS`, once a
      forest-specific model has been trained and validated (see
      `docs/research/ai-methodology.md`). The baselines are honest and
      functional but are not field-validated identification.

## Migrations

```bash
cd backend
alembic upgrade head
```

Run this as part of every deployment, before the new application code starts
serving traffic.

## Health check

`GET /health` reports database connectivity and which AI backend is active
per modality — point your platform's health check at it rather than `GET /`,
which only confirms the process is up.
