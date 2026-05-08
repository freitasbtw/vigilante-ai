#!/usr/bin/env bash
# End-to-end PPE training pipeline (helmet + vest).
#
# Prereqs:
#   - bash ml/setup_local.sh already done
#   - source ml/.venv/bin/activate (or this script does it)
#   - export ROBOFLOW_API_KEY=<your-key>
#
# Usage:
#   bash ml/run_pipeline.sh                 # full run
#   SKIP_DOWNLOAD=1 bash ml/run_pipeline.sh # re-merge + retrain only
#   SKIP_MERGE=1 SKIP_DOWNLOAD=1 bash ml/run_pipeline.sh   # retrain only
#   EPOCHS=80 BATCH=32 bash ml/run_pipeline.sh             # tune
#
# Each step is idempotent: re-runs detect existing artifacts and skip cleanly.

set -euo pipefail

# --- config (override via env) ---
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ML_ROOT="$REPO_ROOT/ml"
DATASETS_DIR="$ML_ROOT/datasets"
MERGED_DIR="$DATASETS_DIR/merged"
URLS_FILE="$ML_ROOT/prepare/roboflow_urls.txt"
# Merge step writes data.yaml with absolute paths — use it directly to avoid
# Ultralytics resolving paths against ~/.config/Ultralytics/settings.json
# (which can point to ComfyUI or other unrelated datasets dir).
CONFIG_TEMPLATE="$ML_ROOT/configs/ppe-cctv-v1.yaml"
CONFIG="$MERGED_DIR/data.yaml"
RUN_NAME="${RUN_NAME:-ppe-canteiro-v1}"
PROJECT_DIR="$ML_ROOT/runs/train"
# WEIGHTS resolved after training (Ultralytics auto-increments dir name when
# RUN_NAME already exists, e.g. ppe-canteiro-v1 -> ppe-canteiro-v1-2).
WEIGHTS=""
RUN_DIR=""
BACKEND_WEIGHTS="$REPO_ROOT/backend/best.pt"

EPOCHS="${EPOCHS:-50}"
BATCH="${BATCH:-16}"
IMGSZ="${IMGSZ:-640}"
MODEL="${MODEL:-yolov8s.pt}"
DEVICE="${DEVICE:-0}"
WORKERS="${WORKERS:-8}"
DEDUPE_THRESHOLD="${DEDUPE_THRESHOLD:-4}"

SKIP_DOWNLOAD="${SKIP_DOWNLOAD:-}"
SKIP_MERGE="${SKIP_MERGE:-}"
SKIP_DEDUPE="${SKIP_DEDUPE:-}"
SKIP_TRAIN="${SKIP_TRAIN:-}"
SKIP_EVAL="${SKIP_EVAL:-}"
SKIP_EXPORT="${SKIP_EXPORT:-}"
SKIP_DEPLOY="${SKIP_DEPLOY:-}"

# --- helpers ---
log() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$*" >&2; }
die() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

cd "$REPO_ROOT"

# --- venv ---
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  if [[ -f "$ML_ROOT/.venv/bin/activate" ]]; then
    log "Activating ml/.venv"
    # shellcheck disable=SC1091
    source "$ML_ROOT/.venv/bin/activate"
  else
    die "No venv found. Run: bash ml/setup_local.sh"
  fi
fi

python -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'" \
  || die "CUDA not available — check driver/toolkit"
python -c "import torch; print(f'GPU: {torch.cuda.get_device_name(0)} ({torch.cuda.get_device_properties(0).total_memory // (1024**3)} GB VRAM)')"

# Override Ultralytics global datasets_dir so it doesn't resolve YAML paths
# against an unrelated location (e.g. ~/comfy/ComfyUI/datasets).
log "Pinning Ultralytics datasets_dir to $DATASETS_DIR"
python - <<PY
from ultralytics.utils import SETTINGS, SETTINGS_FILE
SETTINGS.update({
    "datasets_dir": "$DATASETS_DIR",
    "runs_dir": "$ML_ROOT/runs",
})
print(f"Ultralytics settings: {SETTINGS_FILE}")
print(f"  datasets_dir = {SETTINGS['datasets_dir']}")
print(f"  runs_dir     = {SETTINGS['runs_dir']}")
PY

# ============================================================
# STEP 1 — Download Roboflow datasets
# ============================================================
if [[ -z "$SKIP_DOWNLOAD" ]]; then
  log "STEP 1/6 — Download Roboflow datasets"
  [[ -n "${ROBOFLOW_API_KEY:-}" ]] || die "Set ROBOFLOW_API_KEY first"
  pip show roboflow >/dev/null 2>&1 || pip install -q roboflow
  python -m ml.prepare.roboflow_fetch --from-file "$URLS_FILE" --out-root "$DATASETS_DIR"
else
  log "STEP 1/6 — SKIPPED (SKIP_DOWNLOAD=1)"
fi

# ============================================================
# STEP 2 — Sanity check downloaded datasets
# ============================================================
log "STEP 2/6 — Inspecting downloaded datasets"
shopt -s nullglob
SOURCES=()
for d in "$DATASETS_DIR"/*/; do
  d="${d%/}"
  [[ "$d" == "$MERGED_DIR" ]] && continue
  if [[ -f "$d/data.yaml" ]] || compgen -G "$d/*/data.yaml" > /dev/null; then
    SOURCES+=("$d")
    img_count=$(find "$d" -type f \( -name "*.jpg" -o -name "*.png" -o -name "*.jpeg" \) | wc -l)
    printf "  %-60s %6d images\n" "$(basename "$d")" "$img_count"
  fi
done
shopt -u nullglob
[[ ${#SOURCES[@]} -gt 0 ]] || die "No datasets found in $DATASETS_DIR"

# ============================================================
# STEP 3 — Merge + dedupe into 2-class schema
# ============================================================
if [[ -z "$SKIP_MERGE" ]]; then
  if [[ -z "$SKIP_DEDUPE" ]]; then
    log "STEP 3/6 — Merge + dedupe (threshold=$DEDUPE_THRESHOLD)"
    DEDUPE_FLAGS=(--dedupe --dedupe-threshold "$DEDUPE_THRESHOLD")
  else
    log "STEP 3/6 — Merge (SKIP_DEDUPE=1, ~10x faster)"
    DEDUPE_FLAGS=()
  fi
  rm -rf "$MERGED_DIR"
  python -m ml.prepare.merge_datasets \
    --sources "${SOURCES[@]}" \
    --output "$MERGED_DIR" \
    "${DEDUPE_FLAGS[@]}" \
    --val-ratio 0.15 --test-ratio 0.05

  log "Merged class distribution (train split)"
  python - <<'PY'
from pathlib import Path
from collections import Counter
import os
counts = Counter()
labels = Path(os.environ.get("MERGED_DIR", "ml/datasets/merged")) / "labels" / "train"
for f in labels.glob("*.txt"):
    for line in f.read_text().splitlines():
        parts = line.split()
        if parts:
            counts[parts[0]] += 1
classnames = {"0": "helmet", "1": "vest"}
total = sum(counts.values()) or 1
for cls, n in sorted(counts.items()):
    name = classnames.get(cls, f"class {cls}")
    print(f"  {name:8} {n:8} bboxes ({n/total*100:.1f}%)")
PY
else
  log "STEP 3/6 — SKIPPED (SKIP_MERGE=1)"
fi
export MERGED_DIR

[[ -f "$MERGED_DIR/data.yaml" ]] || die "Merged dataset missing — re-run merge"

# ============================================================
# STEP 4 — Train
# ============================================================
if [[ -z "$SKIP_TRAIN" ]]; then
  log "STEP 4/6 — Train YOLOv8 ($MODEL, $EPOCHS epochs, batch=$BATCH, imgsz=$IMGSZ)"

  # Point YOLO config to the freshly merged dataset
  python -m ml.train \
    --config "$CONFIG" \
    --model "$MODEL" \
    --epochs "$EPOCHS" \
    --batch "$BATCH" \
    --imgsz "$IMGSZ" \
    --device "$DEVICE" \
    --workers "$WORKERS" \
    --project "$PROJECT_DIR" \
    --name "$RUN_NAME"
else
  log "STEP 4/6 — SKIPPED (SKIP_TRAIN=1)"
fi

# Resolve actual run dir (Ultralytics auto-increments: ppe-canteiro-v1, -v1-2, -v1-3, ...).
RUN_DIR=$(ls -dt "$PROJECT_DIR/$RUN_NAME" "$PROJECT_DIR/$RUN_NAME"-* 2>/dev/null \
  | while read -r d; do [[ -f "$d/weights/best.pt" ]] && echo "$d"; done \
  | head -1)
[[ -n "$RUN_DIR" ]] || die "No best.pt under $PROJECT_DIR/$RUN_NAME* — train failed?"
WEIGHTS="$RUN_DIR/weights/best.pt"
log "Resolved run dir: $(basename "$RUN_DIR")"

# ============================================================
# STEP 5 — Eval (test split)
# ============================================================
if [[ -z "$SKIP_EVAL" ]]; then
  log "STEP 5/6 — Evaluate on test split"
  python -m ml.eval \
    --weights "$WEIGHTS" \
    --data "$CONFIG" \
    --split test \
    --device "$DEVICE" \
    --out "$RUN_DIR/eval_test.json"
  cat "$RUN_DIR/eval_test.json"
else
  log "STEP 5/6 — SKIPPED (SKIP_EVAL=1)"
fi

# ============================================================
# STEP 6 — Export + drop into backend
# ============================================================
if [[ -z "$SKIP_EXPORT" ]]; then
  log "STEP 6/6 — Export ONNX + copy to backend/best.pt"
  python -m ml.export --weights "$WEIGHTS" --format onnx --imgsz "$IMGSZ" --device "$DEVICE" || \
    warn "ONNX export failed (training weights still usable)"
fi

if [[ -z "$SKIP_DEPLOY" ]]; then
  cp "$WEIGHTS" "$BACKEND_WEIGHTS"
  log "Copied $WEIGHTS → $BACKEND_WEIGHTS"
fi

log "ALL DONE — restart backend to load new model:  docker compose restart backend"
