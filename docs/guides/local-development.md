# Local development

## Requirements

* Python 3.11+
* Node.js 20+ (22 recommended)
* PostgreSQL 16 + PostGIS, or just use SQLite — both are supported and
  covered by the test suite (see `docs/architecture/database-design.md`)

## Backend + AI engine

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt

cp ../.env.example ../.env           # then edit as needed; SQLite works with no changes

# Apply migrations (creates vanraksha.db if using SQLite)
alembic upgrade head

# Seed reference species, demo users, zones, devices and synthetic
# observations (skip --observations for the full ~260-record dataset)
python ../scripts/seed.py --observations 40

uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for interactive API documentation.

Seeded accounts (development only — see the seed script's log output for the
full list and change these before any real deployment):

| Role | Email | Password |
|---|---|---|
| Admin | `admin@vanraksha.ai` | `ChangeMe#Admin2026` |
| Researcher | `arjun.k@wri-india.org` | `Researcher#2026a` |
| Expert | `anjali.menon@wii.res.in` | `Expert#2026a` |
| Forest officer | `kavitha.raman@forest.gov.in` | `ForestOfficer#2026` |
| Viewer | `viewer@vanraksha.ai` | `Viewer#2026` |

Run the test suite (202 tests, backend + AI engine, ~2.5 minutes):

```bash
cd backend && python -m pytest
```

Lint the whole repository from the root (there is one shared `pyproject.toml`
— do not add a second one under `backend/`, it will silently shadow the root
config for anything under `backend/`):

```bash
ruff check .
```

## Standalone AI microservice (optional)

Only needed if you want to run the AI engine as its own process instead of
in-process with the backend:

```bash
cd ai
pip install -r requirements.txt
uvicorn service.main:app --reload --port 8001
```

Then set `AI_SERVICE_URL=http://localhost:8001` in the backend's `.env` and
restart it — `app/services/ai_client.py` picks this up with no other change.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. `NEXT_PUBLIC_API_URL` (see `.env.example`)
points it at the backend.

## Training the optional trained AI backends

The platform runs fully on the dependency-free baselines (see
`docs/research/ai-methodology.md`). To train the trained backends instead:

```bash
pip install -r ai/requirements-trained.txt

# Vision: classification or detection, Ultralytics YOLO
python -m ai.training.train_vision classify --data path/to/images --out ai/models/weights
python -m ai.training.train_vision detect   --data path/to/dataset.yaml --out ai/models/weights

# Audio: a small spectrogram CNN, split by recording (not by clip)
python -m ai.training.train_audio --data path/to/audio --out ai/models/weights/audio.pt
```

Then point the backend at the resulting checkpoints via `AI_VISION_WEIGHTS`
/ `AI_AUDIO_WEIGHTS` in `.env`.

## Docker Compose

```bash
docker compose up --build
```

Brings up PostgreSQL/PostGIS, the backend, the frontend and the standalone AI
microservice. Run `python scripts/seed.py` against the containerised database
afterwards (`DATABASE_URL=postgresql+psycopg://vanraksha:vanraksha@localhost:5432/vanraksha`).
