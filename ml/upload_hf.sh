#!/usr/bin/env bash
# Upload trained YOLOv8 PPE model to Hugging Face Hub.
#
# Prereqs:
#   - export HF_TOKEN=<your-write-token>      (from https://huggingface.co/settings/tokens)
#   - Trained run exists under ml/runs/train/<name>/
#
# Usage:
#   bash ml/upload_hf.sh                                   # defaults to latest run + auto repo name
#   bash ml/upload_hf.sh ppe-canteiro-v1                   # specific run
#   bash ml/upload_hf.sh ppe-canteiro-v1 myorg/vigilante-ppe   # explicit repo id
#   PRIVATE=1 bash ml/upload_hf.sh                         # private repo
#
# What gets uploaded:
#   - weights/best.pt          (main artifact)
#   - weights/best.onnx        (if exported)
#   - args.yaml                (training params)
#   - results.csv              (epoch metrics)
#   - results.png, confusion_matrix*.png, labels*.jpg, val_batch*.jpg  (visualizations)
#   - README.md                (auto-generated model card)
#   - data.yaml                (class taxonomy — copied from merged dataset)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ML_ROOT="$REPO_ROOT/ml"
RUNS_DIR="$ML_ROOT/runs/train"

log() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
die() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

# --- args ---
RUN_NAME="${1:-}"
REPO_ID="${2:-}"

# Find run directory
if [[ -z "$RUN_NAME" ]]; then
  RUN_DIR=$(ls -dt "$RUNS_DIR"/ppe-* 2>/dev/null | head -1 || true)
  [[ -n "$RUN_DIR" ]] || die "No training run found in $RUNS_DIR. Pass run name as 1st arg."
  RUN_NAME=$(basename "$RUN_DIR")
else
  RUN_DIR="$RUNS_DIR/$RUN_NAME"
fi

[[ -d "$RUN_DIR" ]] || die "Run dir not found: $RUN_DIR"

WEIGHTS="$RUN_DIR/weights/best.pt"
[[ -f "$WEIGHTS" ]] || die "best.pt missing at $WEIGHTS"

# --- env ---
[[ -n "${HF_TOKEN:-}" ]] || die "HF_TOKEN not set (export from https://huggingface.co/settings/tokens)"

# --- venv ---
if [[ -z "${VIRTUAL_ENV:-}" ]] && [[ -f "$ML_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ML_ROOT/.venv/bin/activate"
fi

# Install hub client if missing
python -c "import huggingface_hub" 2>/dev/null || pip install -q "huggingface_hub>=0.20"

# --- resolve repo id ---
if [[ -z "$REPO_ID" ]]; then
  HF_USER=$(python -c "
from huggingface_hub import HfApi
import os
who = HfApi().whoami(token=os.environ['HF_TOKEN'])
print(who['name'])
")
  REPO_ID="${HF_USER}/vigilante-ai-ppe-${RUN_NAME}"
fi

PRIVATE_FLAG="${PRIVATE:+--private}"

log "Run dir   : $RUN_DIR"
log "Repo id   : $REPO_ID  ${PRIVATE_FLAG:+(private)}"
log "Weights   : $WEIGHTS"

# --- generate model card ---
log "Generating README.md model card..."
MERGED_YAML="$ML_ROOT/datasets/merged/data.yaml"
EVAL_JSON="$RUN_DIR/eval_test.json"

python - <<PY
import json, os
from pathlib import Path

run_dir = Path(r"$RUN_DIR")
eval_path = run_dir / "eval_test.json"
results_csv = run_dir / "results.csv"

eval_data = json.loads(eval_path.read_text()) if eval_path.is_file() else {}
mAP50 = eval_data.get("mAP50", "n/a")
mAP5095 = eval_data.get("mAP50-95", "n/a")
precision = eval_data.get("precision", "n/a")
recall = eval_data.get("recall", "n/a")
per_class = eval_data.get("per_class", {})

# Last epoch loss row (results.csv)
last_row = ""
if results_csv.is_file():
    rows = results_csv.read_text().strip().splitlines()
    if len(rows) >= 2:
        last_row = rows[-1]

per_class_lines = "\n".join(
    f"| {name} | {m.get('ap50', 'n/a')} |" for name, m in per_class.items()
) or "| (no per-class data) | |"

card = f"""---
license: agpl-3.0
tags:
  - object-detection
  - yolov8
  - ppe-detection
  - safety
  - construction
library_name: ultralytics
pipeline_tag: object-detection
---

# Vigilante.AI — PPE Detection ($('$RUN_NAME'))

YOLOv8s trained for **construction-site PPE detection** (helmet + safety vest).
Part of the [Vigilante.AI](https://github.com/) workplace-safety platform.

## Classes (2)

| id | name |
|----|------|
| 0 | helmet |
| 1 | vest |

## Test-set metrics

| Metric | Value |
|--------|-------|
| mAP@0.5 | {mAP50} |
| mAP@0.5:0.95 | {mAP5095} |
| Precision | {precision} |
| Recall | {recall} |

### Per-class AP@0.5

| class | AP@0.5 |
|-------|--------|
{per_class_lines}

## Training data

Merged from public PPE datasets (filtered to helmet + vest):
- Personal Protective Equipment Combined Model (Roboflow)
- Hard Hats (Roboflow)
- Hard Hat Universe (Roboflow)
- Safety Vests (Roboflow)
- vest-qf3av (Roboflow)
- vest-pbrbu (Roboflow)

Class imbalance addressed by oversampling vest-only datasets (final ratio ~5:1 helmet:vest).

## Augmentations

YOLO built-ins (mosaic, hsv, perspective=0.0005, scale, fliplr) plus offline Albumentations
(perspective, brightness/contrast, motion blur, downscale, coarse dropout) for CCTV-angle robustness.

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

## Drop into Vigilante.AI backend

```bash
huggingface-cli download {os.environ.get("REPO_ID", "$REPO_ID")} best.pt --local-dir backend/
docker compose restart backend
```

## Last training epoch (raw)

```
{last_row}
```
"""

(run_dir / "README.md").write_text(card)
print(f"Wrote {run_dir / 'README.md'}")
PY

# --- copy data.yaml from merged dataset (class taxonomy) ---
if [[ -f "$MERGED_YAML" ]]; then
  cp "$MERGED_YAML" "$RUN_DIR/data.yaml"
fi

# --- create repo + upload ---
log "Creating + uploading to $REPO_ID ..."
python - <<PY
import os
from pathlib import Path
from huggingface_hub import HfApi, create_repo

api = HfApi(token=os.environ["HF_TOKEN"])
repo_id = "$REPO_ID"
private = bool(os.environ.get("PRIVATE"))
run_dir = Path(r"$RUN_DIR")

create_repo(repo_id, token=os.environ["HF_TOKEN"], private=private, exist_ok=True, repo_type="model")

# Whitelist of files to upload (skip checkpoints, training-only intermediates)
candidates = [
    run_dir / "weights/best.pt",
    run_dir / "weights/best.onnx",
    run_dir / "weights/last.pt",
    run_dir / "args.yaml",
    run_dir / "results.csv",
    run_dir / "results.png",
    run_dir / "data.yaml",
    run_dir / "README.md",
    run_dir / "eval_test.json",
]
candidates += list(run_dir.glob("confusion_matrix*.png"))
candidates += list(run_dir.glob("labels*.jpg"))
candidates += list(run_dir.glob("val_batch*.jpg"))
candidates += list(run_dir.glob("F1_curve.png"))
candidates += list(run_dir.glob("PR_curve.png"))
candidates += list(run_dir.glob("P_curve.png"))
candidates += list(run_dir.glob("R_curve.png"))

uploaded = 0
for path in candidates:
    if not path.is_file():
        continue
    rel = str(path.relative_to(run_dir))
    print(f"  uploading {rel} ({path.stat().st_size // 1024} KB)")
    api.upload_file(
        path_or_fileobj=str(path),
        path_in_repo=rel,
        repo_id=repo_id,
        repo_type="model",
        token=os.environ["HF_TOKEN"],
    )
    uploaded += 1

print(f"\nUploaded {uploaded} files")
print(f"Repo URL: https://huggingface.co/{repo_id}")
PY

log "Done — model live at https://huggingface.co/$REPO_ID"
