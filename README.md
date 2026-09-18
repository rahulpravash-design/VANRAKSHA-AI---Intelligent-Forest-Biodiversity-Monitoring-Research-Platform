# 🌳 VANRAKSHA AI

**An intelligent forest biodiversity monitoring and research platform** —
computer vision, acoustic AI, GIS, IoT and multimodal fusion, built as a
real research system rather than a demo.

> Capture → AI-assisted identification → expert verification → geotagged
> storage → analytics → unusual-pattern detection → research.

## What this is

A researcher photographs or records a species in the field. The platform runs
AI-assisted identification (image, audio, or both fused), geotags the
observation, and routes it to a qualified expert for confirmation. Confirmed
records build a spatial biodiversity dataset that drives dashboards, GIS
maps, diversity indices, and an anomaly detector that flags unusual
observation patterns for a forest officer to investigate — never a
conclusion, always a question for a human.

A model's output is **never** presented as taxonomy: every prediction
carries a confidence, ranked alternatives, the model version, and an explicit
`UNCERTAIN` outcome when the model should not commit. Counts are **detections**,
never population estimates — the sampling design doesn't support that claim,
and the API says so everywhere it matters. See
[`docs/research/ai-methodology.md`](docs/research/ai-methodology.md) for the
full, honest account of what the shipped AI can and cannot do.

## Architecture

```
FOREST → camera / microphone / IoT sensor
             │
             ▼
    Next.js frontend  ──▶  FastAPI backend  ──▶  PostgreSQL/PostGIS
                                 │                  (or SQLite for dev)
                                 ▼
                    AI engine (vision · audio · anomaly · fusion)
                    in-process, or as a standalone microservice
```

See [`docs/architecture/overview.md`](docs/architecture/overview.md) for the
full diagram and [`docs/architecture/database-design.md`](docs/architecture/database-design.md)
for the schema.

| Layer | Stack |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS, react-three-fiber (3D) |
| Backend | FastAPI, SQLAlchemy 2.0, Pydantic v2, JWT auth |
| AI engine | NumPy/Pillow baselines by default; optional PyTorch/Ultralytics trained backends |
| Database | PostgreSQL + PostGIS (production), SQLite (development/tests) |
| GIS | Leaflet + OpenStreetMap, portable haversine spatial queries |

## Quick start

```bash
# Backend + AI engine
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env
alembic upgrade head
python ../scripts/seed.py --observations 40    # demo data; see docs for production
uvicorn app.main:app --reload

# Frontend, in another terminal
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` for the app and `http://localhost:8000/docs` for
the interactive API reference. Full instructions, seeded demo accounts, and
Docker Compose setup: [`docs/guides/local-development.md`](docs/guides/local-development.md).

## Repository layout

```
backend/       FastAPI application — API, database models, services, tests
ai/            The AI engine — vision, audio, anomaly detection, fusion,
               evaluation, and the standalone inference microservice
frontend/      Next.js web application
database/      PostGIS enhancement SQL, migrations (via backend/alembic), seed data
scripts/       seed.py (demo data), bootstrap_admin.py (production admin)
docs/          Architecture, API, research methodology, deployment guides
iot/           Firmware notes and device configuration for field nodes
experiments/   Research experiment run artifacts
```

## Testing

```bash
cd backend && python -m pytest      # 202 tests, backend + AI engine, ~2.5 min
ruff check .                        # from the repo root — one shared lint config
```

## Documentation

- [`docs/architecture/overview.md`](docs/architecture/overview.md) — system architecture
- [`docs/architecture/database-design.md`](docs/architecture/database-design.md) — schema
- [`docs/architecture/security.md`](docs/architecture/security.md) — auth, RBAC, location privacy
- [`docs/research/ai-methodology.md`](docs/research/ai-methodology.md) — what the AI does, honestly
- [`docs/api/README.md`](docs/api/README.md) — API module map and conventions
- [`docs/guides/local-development.md`](docs/guides/local-development.md) — full setup
- [`docs/guides/deployment.md`](docs/guides/deployment.md) — production checklist

## License

MIT — see [`LICENSE`](LICENSE).
