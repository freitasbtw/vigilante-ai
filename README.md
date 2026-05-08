# Vigilante.AI

Real-time PPE compliance monitoring for construction sites and industrial workplaces.
Detects helmets, vests, and missing safety gear from any RTSP stream or local webcam,
surfaces violations through a multi-tenant dashboard, and feeds reviewed alerts back
into a retraining loop.

## Architecture

```
                    ┌────────────────────────────┐
                    │  Frontend (Next.js 14)     │
                    │  /cameras /historico       │
                    │  /relatorios /configuracoes│
                    └──────────────┬─────────────┘
                                   │ JWT (Bearer)
                    ┌──────────────▼─────────────┐
                    │  FastAPI backend           │
                    │  ┌──────────────────────┐  │
   RTSP / webcam ──▶│  │ StreamRegistry       │  │
                    │  │  ├─ StreamSource     │  │
                    │  │  ├─ Detector (YOLO)  │  │
                    │  │  └─ AlertService     │  │
                    │  └──────────┬───────────┘  │
                    │             │              │
                    │  Repositories (SQLAlchemy) │
                    └──────┬──────┬──────┬───────┘
                           │      │      │
                      ┌────▼─┐ ┌──▼──┐ ┌─▼──────┐
                      │ Pg   │ │Blob │ │Prom +  │
                      │ DB   │ │Store│ │Structlog│
                      └──────┘ └─────┘ └────────┘
```

- **Multi-tenant**: each tenant owns its own users, sites, cameras, and alerts.
- **Per-camera workers**: every camera runs an independent `StreamSource` with auto-reconnect.
- **Active learning**: confirmed/false-positive feedback exports to YOLO format for retraining.
- **Backward compatible**: legacy single-camera endpoints (`/api/status`, `/api/alerts`, etc.) proxy to a default camera id.

## Quick start (Docker Compose)

```bash
docker compose up --build              # core stack (postgres, backend, frontend)
docker compose --profile rtsp up -d    # with mediamtx + ffmpeg-loop for RTSP simulation
```

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics

First run: open http://localhost:3000/login, register a user (this creates the tenant), then go to `/cameras` and add your first source.

## Manual setup

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Configure DB + JWT secret
export VIGILANTE_DATABASE_URL="postgresql+psycopg2://vigilante:vigilante@localhost:5432/vigilante"
export VIGILANTE_JWT_SECRET="change-me"

alembic upgrade head
python -m app.main
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

## Auth flow

1. `POST /api/auth/register` with `{email, password, tenant_name}` — creates tenant + first user (admin role).
2. `POST /api/auth/login` returns `{access_token, refresh_token}`.
3. All `/api/cameras/**` and `/api/alerts/**` calls require `Authorization: Bearer <access_token>`.
4. Roles: `admin` (full), `supervisor` (review alerts, configure), `viewer` (read-only).

Open registration is gated by `VIGILANTE_ALLOW_OPEN_REGISTRATION=1`.

## Configuration

All backend vars use the `VIGILANTE_` prefix.

| Variable | Default | Purpose |
|---|---|---|
| `VIGILANTE_DATABASE_URL` | sqlite fallback | Postgres connection string |
| `VIGILANTE_JWT_SECRET` | _required_ | Signing key for access/refresh tokens |
| `VIGILANTE_BLOB_STORAGE_PATH` | `backend/data/alerts` | Where alert frames are persisted |
| `VIGILANTE_RETRAINING_EXPORT_PATH` | `ml/data/feedback` | Where reviewed alerts export as YOLO samples |
| `VIGILANTE_ALLOW_OPEN_REGISTRATION` | `0` | Permit `/api/auth/register` without invite |
| `VIGILANTE_MODEL_PATH` | `best.pt` | YOLO weights served by the detector |
| `VIGILANTE_CONFIDENCE_THRESHOLD` | `0.15` | Minimum detection confidence |
| `VIGILANTE_ALERT_COOLDOWN_SECONDS` | `10` | Per-camera throttle between identical alerts |

Per-camera config (EPI list, color overlays) lives under `/api/cameras/{id}/config/...`.

## API overview

### Auth
- `POST /api/auth/register`, `/login`, `/refresh`
- `GET  /api/auth/me`

### Cameras
- `GET|POST /api/cameras`
- `GET|PATCH|DELETE /api/cameras/{id}`
- `POST /api/cameras/{id}/start`, `/stop`
- `POST /api/cameras/probe` — validate an RTSP URL before saving

### Streams
- `GET /api/cameras/{id}/stream` — MJPEG
- `GET /api/cameras/{id}/stream/frame` — single JPEG

### Alerts
- `GET    /api/cameras/{id}/alerts?status=pending|confirmed|all&page=...`
- `DELETE /api/cameras/{id}/alerts`
- `POST   /api/alerts/{alert_id}/feedback` — `correct | false_positive | none`

### Stats & config
- `GET /api/cameras/{id}/stats`
- `GET|POST /api/cameras/{id}/config/epis`, `/config/colors`

### Legacy single-camera (deprecated, proxies to a default camera)
- `/api/status`, `/api/stream`, `/api/stream/start|stop`, `/api/alerts`, `/api/stats`, `/api/config/epis|colors`

## Frontend pages

| Path | Purpose |
|---|---|
| `/` | Marketing landing |
| `/login` | Sign-in / register |
| `/cameras` | Live preview hub (grid of cameras) |
| `/historico` | Alert history with filters |
| `/relatorios` | Compliance KPIs and charts |
| `/configuracoes` | User profile and tenant settings |
| `/equipe` | Team page |

## Subprojects

- [`ml/`](./ml/README.md) — training pipeline, active-learning loop, Hugging Face publishing.
- [`media/`](./media/README.md) — video files exposed as RTSP for testing without real cameras.
- [`mediamtx/`](./mediamtx/) — RTSP broker config used by the `rtsp` Docker profile.
- [`scripts/`](./scripts/) — RTSP debug utilities (`rtsp-control.sh`, `rtsp-ui.py`).

## Development

```bash
# Backend tests + types
cd backend
pytest -q
mypy app

# Frontend
cd frontend
npm run lint
npm run build

# DB migrations
cd backend
alembic revision --autogenerate -m "<message>"
alembic upgrade head
```

## Tech stack

| Layer | Tooling |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic, OpenCV, Ultralytics YOLOv8 |
| Auth | JWT (python-jose), bcrypt, OAuth2 Bearer |
| Observability | structlog, prometheus-client |
| Frontend | Next.js 14 (App Router), React 18, Tailwind CSS, Radix UI, Recharts |
| Storage | PostgreSQL, local filesystem blobs (S3 swap-in via `BlobStore` protocol) |
| Streaming | mediamtx (RTSP broker), ffmpeg, OpenCV VideoCapture |
| Deployment | Docker Compose |

## License

Proprietary — for educational and FIAP coursework purposes.
