# Vigilante.AI

Monitoramento em tempo real de uso de EPI em canteiros de obra e ambientes industriais.
Detecta capacete, colete e ausência de equipamento de proteção em qualquer stream RTSP
ou webcam local, expõe violações em um painel multi-tenant e realimenta alertas
revisados em um loop de retreinamento.

## Arquitetura

```
                    ┌────────────────────────────┐
                    │  Frontend (Next.js 14)     │
                    │  /cameras /historico       │
                    │  /relatorios /configuracoes│
                    └──────────────┬─────────────┘
                                   │ JWT (Bearer)
                    ┌──────────────▼─────────────┐
                    │  Backend FastAPI           │
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

- **Multi-tenant**: cada tenant tem usuários, sites, câmeras e alertas isolados.
- **Workers por câmera**: cada câmera roda um `StreamSource` independente com auto-reconexão.
- **Active learning**: feedback (correto / falso positivo) gera amostras YOLO para retreino.
- **Compatibilidade**: endpoints legados de uma única câmera (`/api/status`, `/api/alerts`, etc.) seguem funcionando via uma câmera default.

## Como contribuir / rodar localmente (Docker)

**Use Docker. Sempre.** Subir backend, postgres, frontend e mediamtx separados é complicado e cada serviço tem dependência específica (CUDA, libs de vídeo, drivers de webcam). O `docker compose` resolve tudo.

### 1. Subir o stack completo

```bash
git clone https://github.com/badmuriss/vigilante-ai.git
cd vigilante-ai
docker compose up --build
```

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Métricas Prometheus: http://localhost:8000/metrics

### 2. Subir com simulador RTSP (recomendado para desenvolvimento)

Sem câmeras IP reais à mão? Solta vídeos `.mp4` em `media/` e o profile `rtsp` expõe cada um como stream RTSP via mediamtx + ffmpeg-loop.

```bash
docker compose --profile rtsp up -d --build
```

Depois cadastra a câmera em http://localhost:3000/cameras com:
- `source_kind`: `rtsp`
- `rtsp_url`: `rtsp://mediamtx:8554/<nome-do-arquivo-sem-extensao>`

Detalhes em [`media/README.md`](./media/README.md).

### 3. Primeiro acesso

1. Abre http://localhost:3000/login
2. Clica em "Registrar" e cria o primeiro usuário (vira admin do tenant)
3. Vai em `/cameras` e adiciona uma fonte (webcam local, RTSP, ou simulada)
4. Inicia o stream pelo botão da câmera

### 4. Rebuildar após alterações

```bash
docker compose up --build backend       # só backend
docker compose up --build frontend      # só frontend
docker compose restart ffmpeg-loop      # após adicionar vídeos em media/
```

### 5. Volumes persistentes

- `postgres_data` — banco de dados (sobrevive a `docker compose down`)
- `./backend/data/alerts` — frames de alertas (bind mount, dá pra inspecionar)

Para zerar tudo: `docker compose down -v`.

## Setup manual (apenas se Docker não rolar)

> Setup manual existe pra debug profundo. Para contribuir, prefere Docker.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

export VIGILANTE_DATABASE_URL="postgresql+psycopg2://vigilante:vigilante@localhost:5432/vigilante"
export VIGILANTE_JWT_SECRET="troque-isto"

alembic upgrade head
python -m app.main
```

Precisa de Postgres 14+ rodando local. Modelo YOLO em `backend/best.pt` (já versionado).

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

## Fluxo de autenticação

1. `POST /api/auth/register` com `{email, password, tenant_name}` — cria tenant + primeiro usuário (role admin).
2. `POST /api/auth/login` retorna `{access_token, refresh_token}`.
3. Toda chamada em `/api/cameras/**` e `/api/alerts/**` exige `Authorization: Bearer <access_token>`.
4. Roles: `admin` (total), `supervisor` (revisa alertas, configura), `viewer` (só leitura).

Registro aberto controlado por `VIGILANTE_ALLOW_OPEN_REGISTRATION=1`.

## Variáveis de ambiente

Todas usam prefixo `VIGILANTE_`.

| Variável | Default | Descrição |
|---|---|---|
| `VIGILANTE_DATABASE_URL` | sqlite fallback | Connection string do Postgres |
| `VIGILANTE_JWT_SECRET` | _obrigatório_ | Chave de assinatura dos tokens |
| `VIGILANTE_BLOB_STORAGE_PATH` | `backend/data/alerts` | Onde os frames de alerta são salvos |
| `VIGILANTE_RETRAINING_EXPORT_PATH` | `ml/data/feedback` | Destino de amostras YOLO de feedback |
| `VIGILANTE_ALLOW_OPEN_REGISTRATION` | `0` | Permite registro sem convite |
| `VIGILANTE_MODEL_PATH` | `best.pt` | Pesos YOLO carregados pelo detector |
| `VIGILANTE_CONFIDENCE_THRESHOLD` | `0.15` | Confiança mínima de detecção |
| `VIGILANTE_ALERT_COOLDOWN_SECONDS` | `10` | Throttle entre alertas iguais por câmera |

Config por câmera (lista de EPIs, cores) fica em `/api/cameras/{id}/config/...`.

## API resumida

### Auth
- `POST /api/auth/register`, `/login`, `/refresh`
- `GET  /api/auth/me`

### Câmeras
- `GET|POST /api/cameras`
- `GET|PATCH|DELETE /api/cameras/{id}`
- `POST /api/cameras/{id}/start`, `/stop`
- `POST /api/cameras/probe` — valida URL RTSP antes de salvar

### Streams
- `GET /api/cameras/{id}/stream` — MJPEG
- `GET /api/cameras/{id}/stream/frame` — JPEG único

### Alertas
- `GET    /api/cameras/{id}/alerts?status=pending|confirmed|all&page=...`
- `DELETE /api/cameras/{id}/alerts`
- `POST   /api/alerts/{alert_id}/feedback` — `correct | false_positive | none`

### Stats e config
- `GET /api/cameras/{id}/stats`
- `GET|POST /api/cameras/{id}/config/epis`, `/config/colors`

### Legado de câmera única (deprecado, faz proxy para câmera default)
- `/api/status`, `/api/stream`, `/api/stream/start|stop`, `/api/alerts`, `/api/stats`, `/api/config/epis|colors`

## Páginas do frontend

| Rota | Função |
|---|---|
| `/` | Landing institucional |
| `/login` | Entrar / registrar |
| `/cameras` | Hub de câmeras com preview ao vivo |
| `/historico` | Histórico de alertas com filtros |
| `/relatorios` | KPIs de compliance e gráficos |
| `/configuracoes` | Perfil do usuário e tenant |
| `/equipe` | Página da equipe |

## Subprojetos

- [`ml/`](./ml/README.md) — pipeline de treinamento, active learning, publicação no Hugging Face.
- [`media/`](./media/README.md) — vídeos expostos como RTSP para testar sem câmera real.
- [`mediamtx/`](./mediamtx/) — config do broker RTSP usado pelo profile `rtsp`.
- [`scripts/`](./scripts/) — utilitários de debug RTSP (`rtsp-control.sh`, `rtsp-ui.py`).

## Desenvolvimento

```bash
# Testes do backend (dentro do container ou venv)
docker compose exec backend pytest -q
docker compose exec backend mypy app

# Frontend
docker compose exec frontend npm run lint
docker compose exec frontend npm run build

# Migrations
docker compose exec backend alembic revision --autogenerate -m "<mensagem>"
docker compose exec backend alembic upgrade head
```

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic, OpenCV, Ultralytics YOLOv8 |
| Auth | JWT (python-jose), bcrypt, OAuth2 Bearer |
| Observabilidade | structlog, prometheus-client |
| Frontend | Next.js 14 (App Router), React 18, Tailwind CSS, Radix UI, Recharts |
| Storage | PostgreSQL, blobs em filesystem (S3 plugável via protocolo `BlobStore`) |
| Streaming | mediamtx (broker RTSP), ffmpeg, OpenCV VideoCapture |
| Deploy | Docker Compose |

## Licença

Proprietária — uso educacional e trabalho de FIAP.
