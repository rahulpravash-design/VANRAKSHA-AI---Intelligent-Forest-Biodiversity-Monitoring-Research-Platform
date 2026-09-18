# API reference

The full OpenAPI schema is generated from the running application — start
the backend and read it interactively rather than from a hand-maintained
copy that will drift:

```bash
cd backend && uvicorn app.main:app --reload
# then open http://localhost:8000/docs   (Swagger UI)
#      or   http://localhost:8000/redoc  (ReDoc)
#      or   http://localhost:8000/openapi.json (raw schema)
```

## Module map

| Prefix | Router | Covers |
|---|---|---|
| `/api/v1/auth` | `app/api/v1/auth.py` | register, login, refresh, logout, password change, `/me` |
| `/api/v1/users` | `app/api/v1/users.py` | account administration (admin-only creation of any role) |
| `/api/v1/species` | `app/api/v1/species.py` | the biodiversity catalogue; public read, curator write |
| `/api/v1/observations` | `app/api/v1/observations.py` | CRUD, `/capture` (multipart + AI), media, re-identification |
| `/api/v1/ai` | `app/api/v1/ai.py` | model status, standalone identify/fuse calls (nothing stored) |
| `/api/v1/zones` | `app/api/v1/zones.py` | forest zones, zone + observation GeoJSON feeds |
| `/api/v1/analytics` | `app/api/v1/analytics.py` | overview, trends, diversity, zone comparison, seasonal, AI performance, geographic grid, CSV export |
| `/api/v1/verifications` | `app/api/v1/verifications.py` | the expert review queue and AI-vs-expert agreement stats |
| `/api/v1/alerts` | `app/api/v1/alerts.py` | anomaly detection runs, alert lifecycle, device sweeps |
| `/api/v1/sensors` | `app/api/v1/sensors.py` | device registration (officer), sensor ingest (device-authenticated) |
| `/api/v1/research` | `app/api/v1/research.py` | the modality-comparison experiment framework |

## Authentication

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "researcher@vanraksha.ai", "password": "..."}'
# -> {"access_token": "...", "refresh_token": "...", ...}

curl http://localhost:8000/api/v1/observations/me \
  -H 'Authorization: Bearer <access_token>'
```

## Conventions worth knowing before you read the schema

* **List endpoints** return `{"items": [...], "total": N, "limit": L, "offset": O}`
  (`app/schemas/common.py::Page`) — `total` ignores pagination.
* **A model prediction is never a species name alone.** Every prediction
  payload carries `confidence`, `is_uncertain`, `top_k`, the model
  name/version, and `requires_expert_verification: true`. See
  `docs/research/ai-methodology.md`.
* **Coordinates can be generalised.** Any payload with a `latitude`/
  `longitude` also carries `location_generalised: bool`; when true, the
  coordinate has been snapped to a coarse grid because the species is
  threatened or explicitly flagged sensitive and the caller lacks
  precise-location rights. See `docs/architecture/security.md`.
* **Counts are detections, not populations.** Every analytics response with
  a count carries a `disclaimer` or `caveat` field saying so where it
  matters — read it before wiring a chart to "Indian Gaur: 47" and calling
  it a population estimate.
* **Errors** are `{"detail": "...", "fields": {...}}` (validation) or
  `{"detail": "...", "context": {...}}` (domain errors like a role denial) —
  see `app/core/errors.py`.
