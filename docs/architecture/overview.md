# Architecture overview

```
                              FOREST
                                │
                ┌───────────────┼───────────────┐
                ↓               ↓               ↓
           Camera Trap      Microphone      IoT Sensor
                │               │               │
                ↓               ↓               ↓
          Web / Field App  ───────────────  Device ingest
                │                                │
                └───────────────┬────────────────┘
                                 ↓
                          FastAPI backend (backend/app)
                                 │
                ┌────────────────┼────────────────┐
                ↓                ↓                ↓
          PostgreSQL/       AI engine          Object /
          PostGIS or        (ai/, in-process   local storage
          SQLite            or ai/service/     (images, audio,
                             as a microservice) spectrograms)
                                 │
                ┌────────────────┼────────────────┐
                ↓                ↓                ↓
            Vision           Audio            Anomaly +
            pipeline         pipeline         multimodal fusion
                                 │
                                 ↓
                      Observations + AIPrediction rows
                                 │
                ┌────────────────┼────────────────┐
                ↓                ↓                ↓
          Expert review    GIS / map feeds    Analytics +
          workflow         (GeoJSON)          research module
                                 │
                                 ↓
                        Next.js frontend (frontend/)
```

## Processes

| Process | Package | Runs |
|---|---|---|
| API | `backend/app` | `uvicorn app.main:app` |
| AI engine | `ai/` | imported in-process by the backend (default), or `uvicorn ai.service.main:app` as a standalone microservice |
| Frontend | `frontend/` | `next dev` / `next start` |

The backend always talks to the AI engine through `app/services/ai_client.py`.
Setting `AI_SERVICE_URL` switches that gateway from an in-process import to an
HTTP call against the standalone service — nothing else in the backend
changes. This is what lets the AI engine be scaled or GPU-scheduled
independently once trained weights are in use.

## Why the AI engine has a baseline and a trained backend

Every pipeline (`ai/vision`, `ai/audio`) has two backends:

* a **baseline** built only on NumPy and Pillow — a nearest-prototype
  descriptor classifier for images, a template matcher for acoustic features;
* a **trained** backend (Ultralytics YOLO for vision, a small CNN for audio)
  that activates automatically once `AI_VISION_WEIGHTS` / `AI_AUDIO_WEIGHTS`
  point at a checkpoint and the optional dependency is installed.

The whole platform — API, tests, seed data, the research comparison — runs
and is meaningfully exercised with only the baseline, which is what makes it
reproducible on any machine before a forest-specific model exists. See
`docs/research/ai-methodology.md` for what the baseline can and cannot do, and
`ai/training/` for how to replace it.

## Data model

See `docs/architecture/database-design.md` for the full schema. The
short version: `users` → `observations` → `species`, with `ai_predictions`
and `expert_verifications` kept as separate, append-only tables so a model
output is never confused with a human-confirmed identification, and so
AI-versus-expert agreement can be measured after the fact.

## Location privacy

Coordinates of threatened (CR/EN/VU) and explicitly flagged
(`species.is_location_sensitive`) taxa are generalised to a coarse grid for
any viewer without precise-location rights (`ADMIN`, `RESEARCHER`,
`FOREST_OFFICER`, `EXPERT`, or the record's own recorder). This runs in the
serialisation layer (`app/services/geo.py::apply_location_privacy`), not in
individual endpoints, so no route can leak a precise coordinate by forgetting
to ask. See `docs/architecture/security.md`.

## Anomaly detection is a detector, not a verdict

`ai/anomaly` flags **unusual observation-pattern windows** — it never
concludes a cause. `app/services/anomaly_service.py` turns a flagged window
into an `Alert` with ranked *candidate* causes; only a human, closing the
alert, may set `confirmed_cause`. This is enforced, not just documented: the
API refuses to close an alert without resolution notes.
