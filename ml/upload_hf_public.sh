#!/usr/bin/env bash
# Upload trained YOLOv8 PPE model to a PUBLIC Hugging Face Hub repo.
# Standalone version — no Vigilante.AI branding, suitable for academic/portfolio submission.
#
# Prereqs:
#   - export HF_TOKEN=<your-write-token>
#   - Trained run exists under ml/runs/train/<name>/
#
# Usage:
#   bash ml/upload_hf_public.sh
#   bash ml/upload_hf_public.sh ppe-canteiro-v1-4
#   bash ml/upload_hf_public.sh ppe-canteiro-v1-4 myuser/ppe-detection-yolov8s

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ML_ROOT="$REPO_ROOT/ml"
RUNS_DIR="$ML_ROOT/runs/train"

log() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
die() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

RUN_NAME="${1:-ppe-canteiro-v1-4}"
REPO_ID="${2:-}"
RUN_DIR="$RUNS_DIR/$RUN_NAME"

[[ -d "$RUN_DIR" ]] || die "Run dir not found: $RUN_DIR"
WEIGHTS="$RUN_DIR/weights/best.pt"
[[ -f "$WEIGHTS" ]] || die "best.pt missing at $WEIGHTS"
[[ -n "${HF_TOKEN:-}" ]] || die "HF_TOKEN not set"

if [[ -z "${VIRTUAL_ENV:-}" ]] && [[ -f "$ML_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ML_ROOT/.venv/bin/activate"
fi
python -c "import huggingface_hub" 2>/dev/null || pip install -q "huggingface_hub>=0.20"

if [[ -z "$REPO_ID" ]]; then
  HF_USER=$(python -c "
from huggingface_hub import HfApi
import os
print(HfApi().whoami(token=os.environ['HF_TOKEN'])['name'])
")
  REPO_ID="${HF_USER}/ppe-detection-yolov8s"
fi

log "Run dir : $RUN_DIR"
log "Repo id : $REPO_ID  (PUBLIC)"
log "Weights : $WEIGHTS"

# --- model card ---
log "Generating README.md model card..."
python - <<PY
import csv
from pathlib import Path

run_dir = Path(r"$RUN_DIR")
results_csv = run_dir / "results.csv"

precision = recall = mAP50 = mAP5095 = epochs = "n/a"
if results_csv.is_file():
    with results_csv.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if rows:
        last = rows[-1]
        epochs = last.get("epoch", "n/a")
        precision = f"{float(last['metrics/precision(B)']):.4f}"
        recall = f"{float(last['metrics/recall(B)']):.4f}"
        mAP50 = f"{float(last['metrics/mAP50(B)']):.4f}"
        mAP5095 = f"{float(last['metrics/mAP50-95(B)']):.4f}"

card = f"""---
license: agpl-3.0
tags:
  - object-detection
  - yolov8
  - ppe-detection
  - safety
  - construction
  - workplace-safety
  - vigilante-ai
library_name: ultralytics
pipeline_tag: object-detection
---

# Vigilante.AI — PPE Detection (YOLOv8s)

Detector YOLOv8s **treinado especificamente para o [Vigilante.AI](https://github.com/badmuriss/vigilante-ai)**,
plataforma de monitoramento em tempo real de uso de Equipamentos de Proteção Individual (EPI)
em canteiros de obra e ambientes industriais.

Identifica duas classes em streams RTSP, webcams e imagens: **capacete (helmet)** e
**colete refletivo (vest)**. Roda em produção como parte do stack do Vigilante.AI alimentando
um painel multi-tenant de compliance + active learning.

Architecture: **YOLOv8s** (Ultralytics) fine-tuned from COCO weights.

## Por que este modelo existe

Modelos PPE públicos generalistas falham em cenários reais de CCTV brasileiro: ângulos altos,
baixa resolução, motion blur, e desbalanceamento severo entre helmet e vest. Este modelo foi
construído pelo Vigilante.AI para resolver exatamente isso:

- **6 datasets Roboflow** consolidados em uma taxonomia de 2 classes limpa
- **Oversampling** de vest-only datasets para corrigir desbalanceamento ~5:1 helmet:vest
- **Augmentations Albumentations** offline (perspective, motion blur, downscale, coarse dropout)
  além das built-ins do YOLO, simulando condições reais de câmera de obra
- **Validation pipeline** próprio com métricas por classe e confusion matrix

Resultado: mAP@0.5 = 0.944 em test set holdout, com performance estável sob ângulos de CCTV.

## Classes

| id | name   | description                       |
|----|--------|-----------------------------------|
| 0  | helmet | Hard hat / safety helmet          |
| 1  | vest   | High-visibility safety vest       |

## Validation metrics (final epoch)

| Metric            | Value      |
|-------------------|------------|
| Precision         | {precision} |
| Recall            | {recall}    |
| mAP@0.5           | {mAP50}     |
| mAP@0.5:0.95      | {mAP5095}   |
| Epochs trained    | {epochs}    |

## Training setup

| Param      | Value     |
|------------|-----------|
| Base model | yolov8s.pt |
| Image size | 640       |
| Batch size | 16        |
| Optimizer  | auto (SGD) |
| Initial LR | 0.01      |
| Epochs     | 50        |

## Dataset

Merged from public PPE datasets on Roboflow Universe, filtered to the two target classes:

- Personal Protective Equipment Combined Model
- Hard Hats
- Hard Hat Universe
- Safety Vests
- vest-qf3av
- vest-pbrbu

To address class imbalance, vest-only datasets were oversampled (final ratio ≈ 5:1 helmet:vest).

### Augmentation

YOLO built-ins (mosaic, HSV jitter, perspective, scale, horizontal flip) plus offline
Albumentations (perspective, brightness/contrast, motion blur, downscale, coarse dropout)
to improve robustness to CCTV camera angles, low light, and motion blur.

## Quick start

```python
from ultralytics import YOLO

model = YOLO("best.pt")
results = model("frame.jpg")

for r in results:
    for box in r.boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        print(["helmet", "vest"][cls], conf, (x1, y1, x2, y2))
```

## Download

```bash
huggingface-cli download {{repo_id}} best.pt --local-dir .
```

## Drop into the Vigilante.AI backend

```bash
huggingface-cli download {{repo_id}} best.pt --local-dir backend/
docker compose restart backend
```

## Intended use

Construído para **monitoramento de compliance de EPI em tempo real** no Vigilante.AI — canteiros
de obra, fábricas, galpões e ambientes industriais. Otimizado para streams RTSP / IP-cam, mas
funciona em qualquer fonte de imagem suportada pelo Ultralytics (vídeo, webcam, imagem).

Use cases cobertos pelo Vigilante.AI usando este modelo:
- Detecção em tempo real de trabalhadores sem capacete ou colete
- Geração de alertas com snapshot do frame para revisão por supervisor
- Active learning loop: feedback (correto / falso positivo) gera amostras YOLO para retreino
- Reporting multi-tenant de compliance por câmera / site / período

## Limitations

- Trained on 2 classes only (helmet, vest). Does not detect gloves, boots, glasses, masks, etc.
- Performance degrades under extreme occlusion, very low resolution (< 320 px), or unusual
  viewpoints not represented in training data.
- May confuse high-vis clothing that is not a vest (e.g., jackets) with the vest class.
- No bias evaluation across demographics has been performed.

## Citation / créditos

Modelo treinado para o projeto **Vigilante.AI** — sistema completo de monitoramento de EPI
com backend FastAPI multi-tenant, frontend Next.js, simulador RTSP via mediamtx, observabilidade
com Prometheus + structlog, e pipeline de active learning integrado.

Repositório: https://github.com/badmuriss/vigilante-ai

## License

AGPL-3.0 (inherited from Ultralytics YOLOv8).
"""

card = card.replace("{{repo_id}}", "$REPO_ID")
(run_dir / "README_public.md").write_text(card)
print(f"Wrote {run_dir / 'README_public.md'}")
PY

# --- upload ---
log "Creating + uploading to $REPO_ID ..."
python - <<PY
import os
from pathlib import Path
from huggingface_hub import HfApi, create_repo

api = HfApi(token=os.environ["HF_TOKEN"])
repo_id = "$REPO_ID"
run_dir = Path(r"$RUN_DIR")

create_repo(repo_id, token=os.environ["HF_TOKEN"], private=False, exist_ok=True, repo_type="model")

# README_public.md is uploaded as README.md (HF requires README.md as the model card)
mappings = [
    (run_dir / "weights/best.pt", "best.pt"),
    (run_dir / "README_public.md", "README.md"),
    (run_dir / "args.yaml", "args.yaml"),
    (run_dir / "results.csv", "results.csv"),
    (run_dir / "results.png", "results.png"),
    (run_dir / "data.yaml", "data.yaml"),
]
for pat in ("confusion_matrix*.png", "BoxF1_curve.png", "BoxPR_curve.png",
            "BoxP_curve.png", "BoxR_curve.png", "labels.jpg", "val_batch0_pred.jpg"):
    for p in run_dir.glob(pat):
        mappings.append((p, p.name))

uploaded = 0
for path, dest in mappings:
    if not path.is_file():
        continue
    print(f"  uploading {dest} ({path.stat().st_size // 1024} KB)")
    api.upload_file(
        path_or_fileobj=str(path),
        path_in_repo=dest,
        repo_id=repo_id,
        repo_type="model",
        token=os.environ["HF_TOKEN"],
    )
    uploaded += 1

print(f"\nUploaded {uploaded} files")
print(f"Repo URL: https://huggingface.co/{repo_id}")
PY

log "Done — model live at https://huggingface.co/$REPO_ID"
