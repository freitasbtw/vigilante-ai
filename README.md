# Vigilante.AI

Vigilante.AI is a real-time workplace safety monitoring system powered by computer vision.
It detects PPE usage from camera frames and surfaces violations in a live dashboard.

## Stack

- Backend: Python 3.11+, FastAPI, OpenCV, Ultralytics YOLOv8
- Frontend: Next.js 14, React 18, Tailwind CSS
- Deployment: Docker Compose

## PPE classes

Current model contract uses 6 PPE classes:

- `luvas`
- `colete`
- `protecao_ocular`
- `capacete`
- `mascara`
- `calcado_seguranca`

## Quick start (Docker)

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs

## Local development

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.main
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

## Validation checks

Run these before opening a PR:

```bash
# backend
cd backend
python -m pytest -q

# frontend
cd frontend
npm run lint
npm run build
```

## Environment variables

All backend vars use `VIGILANTE_` prefix.

- `VIGILANTE_CAMERA_INDEX` (default: `0`)
- `VIGILANTE_MODEL_PATH` (default: `best.pt`)
- `VIGILANTE_CONFIDENCE_THRESHOLD` (default: `0.15`)
- `VIGILANTE_MODEL_INPUT_SIZE` (default: `512`)
- `VIGILANTE_CAMERA_WIDTH` (default: `640`)
- `VIGILANTE_CAMERA_HEIGHT` (default: `480`)
- `VIGILANTE_ALERT_COOLDOWN_SECONDS` (default: `10`)

## API overview

- `GET /api/status`: camera/model/fps/uptime status
- `GET /api/stream/frame`: latest JPEG frame
- `POST /api/stream/start`: start processing
- `POST /api/stream/stop`: stop processing
- `GET /api/alerts`: latest alerts (max 50)
- `DELETE /api/alerts`: clear alerts
- `GET /api/stats`: session stats
- `GET /api/config/epis`: list EPI toggles
- `POST /api/config/epis`: update active EPIs
