# Vigilante.AI — Próximos passos pós-treinamento

Runbook ordenado: do treino terminar até demo rodando + modelo publicado no Hugging Face.

---

## 0. Estado esperado no fim do treino

`run_pipeline.sh` imprime:

```
ALL DONE — restart backend to load new model: docker compose restart backend
```

Confirma artefatos gerados:

```bash
RUN=ml/runs/train/$(ls -t ml/runs/train | head -1)
ls -lh "$RUN/weights/"        # best.pt, last.pt, talvez best.onnx
cat "$RUN/eval_test.json"     # métricas test set
```

`run_pipeline` já copia `best.pt` → `backend/best.pt` automático. Modelo novo pronto pra uso.

---

## 1. Validar resultado do treino

### 1.1 mAP por classe

```bash
cat "$RUN/eval_test.json"
```

Critério ship:

| Métrica | Mínimo | Bom |
|---------|--------|-----|
| mAP@0.5 global | 0.85 | ≥ 0.92 |
| helmet AP@0.5 | 0.90 | ≥ 0.95 |
| vest AP@0.5 | 0.65 | ≥ 0.80 |
| recall global | 0.75 | ≥ 0.85 |

Se vest AP < 0.65 → **plano B** (oversample vest images + retreino 20 epochs antes de seguir).

### 1.2 Visualizações (sanity check humano)

```bash
xdg-open "$RUN/results.png"             # curvas loss + mAP
xdg-open "$RUN/confusion_matrix.png"    # erros entre helmet/vest
xdg-open "$RUN/val_batch0_pred.jpg"     # predições reais lado a lado com labels
```

Olha:
- Curvas mAP devem estar planas no fim (convergiu, não cortou cedo)
- Confusion matrix: diagonal forte, pouco off-diagonal
- val_batch: bboxes colados nos objetos certos

---

## 2. Baixar vídeo canteiro pra teste local

Sem cliente real ainda → vídeo YouTube simula câmera CCTV.

```bash
mkdir -p media

# Sugestão de buscas que rendem CCTV-style:
#   construction site time lapse 4k
#   highrise construction webcam
#   obra construção time lapse Brasil
#   aerial construction site fixed camera

yt-dlp -f "best[ext=mp4][height<=720]" \
  "<youtube-url>" \
  -o "media/canteiro.mp4"

# Confere
ls -lh media/canteiro.mp4   # algo entre 50-500MB
```

Pode jogar múltiplos: `media/canteiro1.mp4`, `media/obra-sp.mp4`, etc — cada um vira stream RTSP separado.

---

## 3. Subir stack completa

Profile `rtsp` adiciona MediaMTX + ffmpeg-loop ao stack base:

```bash
docker compose --profile rtsp up -d --build
```

Aguarda ~30s. Confere todos serviços:

```bash
docker compose ps
```

Esperado:

```
NAME                              STATUS
vigilante-ai-postgres-1           Up (healthy)
vigilante-ai-backend-1            Up
vigilante-ai-frontend-1           Up
vigilante-ai-mediamtx-1           Up
vigilante-ai-ffmpeg-loop-1        Up
```

---

## 4. Validar cada camada

### 4.1 Postgres
```bash
docker exec vigilante-ai-postgres-1 pg_isready -U vigilante
# expected: accepting connections
```

### 4.2 Backend health + modelo
```bash
curl -s http://localhost:8000/api/status | jq
docker compose logs backend | grep "PPE model loaded"
# expected: "PPE model loaded with 2 classes: {'helmet', 'vest'}"
```

### 4.3 RTSP server
```bash
curl -s http://localhost:9997/v3/paths/list | jq '.items[].name'
# expected: lista nomes dos vídeos em ./media (sem extensão)
```

### 4.4 Stream válido
```bash
ffprobe rtsp://localhost:8554/canteiro 2>&1 | grep -E "Video|Duration"
# expected: linhas Video: h264, fps, ...
```

### 4.5 Browser HLS (visual)
Abre: `http://localhost:8888/canteiro/index.m3u8`
Se baixar `.m3u8` → stream rodando.

Qualquer falha → `docker compose logs <service>` + me avisa.

---

## 5. Login + cadastrar câmera no UI

http://localhost:3000/login

### 5.1 Criar conta (1ª vez)
- Aba "Criar conta"
- Email + senha (≥8 chars) + nome do tenant
- Submit → redireciona pra `/cameras`

### 5.2 Adicionar câmera RTSP
`/cameras` → "Adicionar câmera":

| Campo | Valor |
|-------|-------|
| Nome | `Canteiro teste` |
| Tipo | `RTSP (câmera IP)` |
| URL RTSP | `rtsp://mediamtx:8554/canteiro` |
| Local | `Demo` |

> URL: `mediamtx` quando backend está no compose. `localhost` quando backend roda fora.

Clica "Testar" → deve dar `✓ OK (1280x720)` (ou similar).

Salva.

### 5.3 Iniciar stream
Card da câmera → botão "Iniciar". Status muda pra `online` (badge verde) em 2-3s.

```bash
# Confirma backend pegou
docker compose logs -f backend | grep -i "stream\|source"
```

---

## 6. Ver detecção em tempo real

http://localhost:3000/monitor

- Frame ao vivo com bounding boxes:
  - Verde + `Capacete` quando detecta capacete
  - Verde + `Colete` quando detecta colete
  - Vermelho + ⚠ quando há violação

### 6.1 Configurar EPIs fiscalizados
Painel direito → toggles:
- ☑ Capacete
- ☑ Colete

Sem toggles ativos = sistema só detecta, não gera alertas.
Com toggles = ausência → alerta.

### 6.2 Ver alertas persistidos
`/alerts` → lista paginada com:
- Timestamp
- Tipo (capacete ausente, colete ausente)
- Confiança
- Frame thumbnail (click → modal full-res)

### 6.3 Stats agregadas
`/dashboard`:
- Total violações
- Compliance rate (% frames sem violação)
- Timeline por minuto

---

## 7. Validar persistência

```bash
docker compose restart backend
# Re-login no browser
# Câmeras + alertas devem continuar (Postgres + filesystem)
```

---

## 8. Subir modelo pro Hugging Face

### 8.1 Garante token
```bash
echo $HF_TOKEN | head -c 10
# se vazio: export HF_TOKEN=hf_xxx (de https://huggingface.co/settings/tokens — write scope)
```

### 8.2 Upload
```bash
bash ml/upload_hf.sh
# default: usa run mais recente, repo público <seu-user>/vigilante-ai-ppe-<run-name>

# privado:
PRIVATE=1 bash ml/upload_hf.sh

# nome custom:
bash ml/upload_hf.sh ppe-canteiro-v1-3 myorg/vigilante-ppe-helmet-vest
```

Sobe:
- `best.pt` + `last.pt` + `best.onnx` (se exportado)
- `args.yaml`, `results.csv`, plots (`results.png`, `confusion_matrix.png`, etc)
- `data.yaml`, `eval_test.json`
- `README.md` model card auto-gerado (com mAP, classes, snippet Python)

URL final: `https://huggingface.co/<seu-user>/vigilante-ai-ppe-<run-name>`

### 8.3 Pull em outra máquina (prod AWS futuro)
```bash
huggingface-cli download <user>/vigilante-ai-ppe-<run> best.pt --local-dir backend/
docker compose restart backend
```

---

## 9. Métricas observability (opcional)

```bash
# Métricas Prometheus
curl -s http://localhost:8000/metrics | grep vigilante

# Tempo real GPU + RAM
watch -n 2 'nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv; free -h'
```

---

## 10. Iteração — quando precisar melhorar modelo

### 10.1 Se vest mAP < 0.70

**Plano B** — oversample vest:

```bash
# Adicionar mais datasets vest-only (busca Roboflow Universe)
# Editar ml/prepare/roboflow_urls.txt + adicionar URLs

# Re-baixa só os novos + remerge + retreina (sem download dos antigos)
SKIP_DOWNLOAD=  bash ml/run_pipeline.sh
# (download skippa os já existentes, baixa só novos)
```

### 10.2 Active learning depois de piloto real

Quando vídeo de canteiro real do cliente acumular violações em `backend/data/alerts/`:

```bash
python -m ml.active_learning.sample_uncertain \
  --weights backend/best.pt \
  --frames-dir backend/data/alerts \
  --out ml/datasets/active_learning_v1 \
  --max-samples 500 \
  --max-conf 0.6
```

Anota no Label Studio (ver `ml/active_learning/label_studio_setup.md`), mistura no merge:

```bash
# Adiciona ml/datasets/active_learning_v1 ao --sources do run_pipeline.sh
SKIP_DOWNLOAD=1 bash ml/run_pipeline.sh
```

Continual learning: re-treina mensal com 500 frames novos.

### 10.3 Otimização inferência

Após modelo bom (mAP ≥ 0.92):

```bash
# CPU: INT8 ONNX (3x speedup, perda 2-5% mAP)
python -m ml.export --weights backend/best.pt --format onnx --int8 \
  --data ml/datasets/merged/data.yaml

# GPU prod (T4 AWS): TensorRT FP16 (3-5x speedup)
python -m ml.export --weights backend/best.pt --format engine --half
```

---

## 11. Próximos macro-passos do produto

Já entregues nesse repo:
- ✅ Multi-stream RTSP backend
- ✅ Postgres persistência
- ✅ Auth JWT + multi-tenancy
- ✅ Frontend cameras CRUD
- ✅ Observability (structlog + Prometheus)
- ✅ Pipeline ML reproduzível
- ✅ Upload HF script

Falta pra produção AWS:
- [ ] Trocar `LocalBlobStore` → `S3BlobStore` (interface já preparada)
- [ ] Trocar JWT → Cognito Federated Identity
- [ ] AWS Kinesis Video Streams ingestão (vs RTSP direto local)
- [ ] EC2 G4dn (Tesla T4) com modelo TensorRT
- [ ] CloudFront + ACM TLS
- [ ] CI/CD pipeline (GitHub Actions → ECS Fargate)
- [ ] Sentry SDK (error tracking)
- [ ] Stripe billing integration

Falta pra produto comercial:
- [ ] Página /reports com PDF compliance NR-6/NR-18
- [ ] Notificação push (mobile / WhatsApp / email)
- [ ] Mapa geo dos canteiros (PostGIS)
- [ ] Tracking ByteTrack (reduz alertas duplicados ~40%)
- [ ] Blur facial automático antes de persistir frame (LGPD)
- [ ] Frontend: grid N×N de monitor (várias câmeras simultâneas)
- [ ] Backend: API key per-tenant (integração externa)

---

## TL;DR comandos

```bash
# Após treino terminar:
cat ml/runs/train/$(ls -t ml/runs/train | head -1)/eval_test.json   # 1. validar mAP

mkdir -p media && \
  yt-dlp -f "best[ext=mp4][height<=720]" "<URL>" -o media/canteiro.mp4   # 2. vídeo

docker compose --profile rtsp up -d --build                          # 3. sobe stack
docker compose ps                                                     # 4. valida

# Browser:
# - http://localhost:3000/login → cria conta
# - /cameras → adiciona rtsp://mediamtx:8554/canteiro → testar → salvar → iniciar
# - /monitor → ver detecção em tempo real

bash ml/upload_hf.sh                                                  # 5. publica modelo
```
