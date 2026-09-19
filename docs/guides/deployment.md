# Deployment notes

This is a checklist of what changes between local development and a real
deployment, plus one worked example of a hosted split (API on Render, frontend
on Vercel). Any provider that runs a container and a Postgres instance works —
nothing below is Render-specific except `render.yaml`.

## A worked example: API on Render, frontend on Vercel

The two halves deploy independently and only need to learn each other's URL.

1. **API + database.** `render.yaml` at the repository root is a Render
   blueprint: create a Blueprint instance from this repo and it provisions
   Postgres, builds `backend/Dockerfile`, and serves the API. It leaves four
   values for you to fill in (`STORAGE_PUBLIC_BASE_URL`,
   `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD`, and `CORS_ORIGINS` if
   your frontend is not on one of the default Vercel URLs). Migrations run
   automatically on every boot — see `backend/docker-entrypoint.sh`.
2. **Frontend.** Deploy `frontend/` to Vercel with root directory `frontend`,
   then set `NEXT_PUBLIC_API_URL` to the API's public origin (no trailing
   slash, no `/api/v1` — `NEXT_PUBLIC_API_PREFIX` supplies that) and redeploy.
   Until this is set the frontend defaults to `http://localhost:8000` and a
   hosted build will fail every request.
3. **Close the loop.** Add the frontend's origin to the API's `CORS_ORIGINS`
   and set `STORAGE_PUBLIC_BASE_URL` to `https://<your-api-host>/media`, so
   media URLs in API responses resolve.

A driverless `DATABASE_URL` (`postgres://…` or `postgresql://…`, which is what
most managed Postgres hosts hand out) is accepted: `Settings` pins it to the
psycopg 3 dialect, since that is the only Postgres driver installed.

## Frontend-only builds (demo mode)

A frontend deployed without `NEXT_PUBLIC_API_URL` serves a **demo build**: it
answers reads from `frontend/public/demo/data.json` instead of an API, labels
itself as sample data, and explains that writes cannot be saved.

This exists because the variable is inlined at build time, so a frontend built
without it would otherwise ship pointing at `http://localhost:8000` and fail
every request for every visitor. `isDemoMode()` in `lib/config.ts` detects that
case — a loopback API address on a page served from somewhere else — so no
build-time flag is needed. Force it either way with `NEXT_PUBLIC_DEMO_MODE=1`
or `0`.

The payloads are snapshots of real responses from a seeded instance, not
hand-written fixtures, so they cannot drift from the API's actual shapes.
Regenerate them by running a seeded API locally and then:

```bash
python scripts/capture_demo_data.py \
    frontend/public/demo/data.json frontend/public/demo/media backend/storage
```

Audio is deliberately excluded (the synthetic WAVs are ~24MB); spectrograms
are kept, so acoustic observations still show their evidence. Setting
`NEXT_PUBLIC_API_URL` to a real backend disables all of this — the same build
then talks only to that API.

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
- [ ] **`DATABASE_URL`** — a managed PostgreSQL instance. PostGIS is not
      required: spatial queries use the portable haversine implementation in
      `app/services/geo.py`. Where the extension is available, applying
      `database/postgis/001_spatial.sql` adds generated geometry columns and
      spatial indexes so large observation tables can use native operators.
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
serving traffic. Container deployments get it for free:
`backend/docker-entrypoint.sh` runs it before starting uvicorn, and
`alembic upgrade head` is a no-op once the database is already at head.

## Health check

`GET /health` reports database connectivity and which AI backend is active
per modality — point your platform's health check at it rather than `GET /`,
which only confirms the process is up.
