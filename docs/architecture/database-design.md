# Database design

15 tables, in `backend/app/models/`. Portable across SQLite (development,
tests) and PostgreSQL/PostGIS (production) — every enum is a value-backed
`VARCHAR` with a `CHECK` constraint (`app/models/enums.py::sa_enum`) rather
than a native Postgres enum, and every JSON column uses `none_as_null=True`
so an absent value is SQL `NULL` on both backends.

## Core entities

```
users ──< observations >── species
              │
              ├──< media_assets
              ├──< ai_predictions >── species (predicted_species_id)
              └──< expert_verifications >── users (expert_id)
                                        └── species (corrected_species_id)

forest_zones ──< observations
             ──< devices ──< sensor_readings
             ──< anomaly_scores ──< alerts

experiments ──< experiment_runs

audit_logs, revoked_tokens: append-only, no foreign relationships back out
```

## Why AI predictions and observations are separate tables

`observations.species_id` is **only ever set by a human** — the recorder at
capture time. A model's opinion lives in `ai_predictions` (one row per
inference, so re-running a newer model version never overwrites the history
of what an earlier version said) and is mirrored onto
`observations.ai_prediction` / `ai_confidence` / `ai_predicted_species_id`
purely for cheap listing. `observations.verified_species_id` is set only by
`expert_verifications`. This separation is what makes
"AI-versus-expert agreement" a real, queryable thing
(`app/services/verification_service.py::agreement_stats`) instead of a number
that has to trust that nobody ever overwrote the evidence.

`Observation.final_species_id` (a Python property, not a column) is the
single field anything doing analysis should read: verified species when
reviewed, the recorder's report while still pending, `None` once rejected.

## Location data

`observations.latitude` / `longitude` are plain floats, indexed, with
`CHECK` constraints keeping them in range. Spatial queries
(`app/services/geo.py`) use the haversine formula expressed in SQL with a
bounding-box pre-filter, which is dialect-portable and index-friendly without
needing PostGIS. `database/postgis/001_spatial.sql` optionally adds generated
`geometry` columns and GiST indexes for a PostgreSQL deployment that wants
native spatial operators at scale — nothing in the application requires it.

## Key constraints worth knowing about

* `ai_predictions.confidence`, `observations.ai_confidence` — `CHECK (0–1)`.
* `observations.latitude/longitude` — `CHECK` range constraints.
* `species.scientific_name` — unique, normalised to `Genus species` casing
  (`species_service.py::normalise_scientific_name`) before the uniqueness
  check, so `"BOS GAURUS"` and `"Bos gaurus"` collide as intended.
* `media_assets.checksum` — SHA-256 of the file; storage is content-addressed
  (`app/services/storage.py`), so identical uploads are stored once.
* `devices.ingest_key_hash` — a field node's credential is hashed like a
  password and shown to the caller exactly once, at registration.

## Migrations

Alembic, configured in `backend/alembic/`, reading `settings.database_url`
(never a URL hardcoded in `alembic.ini`). Generate a migration after changing
a model:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```
