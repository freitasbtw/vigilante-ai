# Vigilante.AI — ML Training Pipeline

PPE detection model retraining for **CCTV-angle imagery** (top-down, wide-angle,
low-resolution security cameras) — distinct from frontal/selfie images that
the bootstrap `best.pt` was trained on.

## Layout

```
ml/
├── datasets/                      # Downloaded datasets (gitignored)
├── weights/                       # Pretrained YOLO base weights (gitignored)
├── runs/                          # Training output (gitignored)
├── configs/
│   ├── ppe-cctv-v1.yaml           # YOLO data config (paths, classes)
│   └── augment.yaml               # Albumentations pipeline config
├── train.py                       # CLI: train YOLOv8 on the merged CCTV dataset
├── eval.py                        # mAP per class + confusion matrix
├── export.py                      # ONNX, TensorRT, INT8
├── run_pipeline.sh                # End-to-end: fetch → merge → train → eval → export
├── setup_local.sh                 # One-shot CUDA env + venv
├── upload_hf.sh                   # Publish weights + model card to Hugging Face
├── prepare/
│   ├── DATASETS.md                # Selection guide + curl-verified URLs
│   ├── voc_to_yolo.py             # Pascal VOC → YOLO converter (SHWD, GDUT-HWD)
│   ├── merge_datasets.py          # Unify class taxonomies → 2-class schema + dedupe
│   ├── roboflow_fetch.py          # Roboflow SDK CLI wrapper
│   └── roboflow_urls.txt          # Stable Roboflow project list
├── augment/
│   └── pipeline.py                # Albumentations transforms (perspective, blur, downscale)
├── active_learning/
│   ├── sample_uncertain.py        # Pull low-confidence frames from production
│   └── label_studio_setup.md      # How to deploy Label Studio locally
├── data/feedback/
│   ├── confirmed/                 # Annotated true positives (images + YOLO labels)
│   ├── rejected/                  # Annotated false positives (empty labels)
│   └── merged/                    # Output of merge_feedback.sh
└── scripts/
    └── merge_feedback.sh          # Fold feedback into the active train split
```

## Quick start

### One-shot pipeline (recommended)

```bash
bash ml/setup_local.sh             # creates ml/.venv, installs torch + ultralytics + roboflow
source ml/.venv/bin/activate
export ROBOFLOW_API_KEY=...        # required for prepare.roboflow_fetch
bash ml/run_pipeline.sh            # fetch → merge → train → eval → export
```

`run_pipeline.sh` chains the six steps below. Run individual steps when iterating.

### Step-by-step

```bash
# 1. Fetch Roboflow datasets (uses ROBOFLOW_API_KEY)
python -m ml.prepare.roboflow_fetch --urls ml/prepare/roboflow_urls.txt --out ml/datasets

# 2. Convert VOC → YOLO where needed (SHWD, GDUT)
python -m ml.prepare.voc_to_yolo \
  --voc-root ml/datasets/shwd_raw \
  --out-root ml/datasets/shwd

# 3. Merge into 2-class schema (helmet / vest) with dedupe + train/val/test split
python -m ml.prepare.merge_datasets \
  --sources ml/datasets/* \
  --output ml/datasets/merged --dedupe

# 4. Train (RTX 4070 Super: ~3-4h for 50 epochs)
python -m ml.train --config ml/configs/ppe-cctv-v1.yaml --epochs 50 --batch 16

# 5. Eval mAP per class + confusion matrix
python -m ml.eval --weights runs/train/ppe-cctv-v1/weights/best.pt --data ml/configs/ppe-cctv-v1.yaml

# 6. Export (ONNX or TensorRT INT8)
python -m ml.export --weights runs/train/ppe-cctv-v1/weights/best.pt --format onnx

# 7. Drop into backend
cp runs/train/ppe-cctv-v1/weights/best.pt backend/best.pt
```

## Active learning loop

Once a model is in production, sample low-confidence frames and feed corrections back:

```bash
# 1. Score recent alerts and export uncertain frames to Label Studio
python -m ml.active_learning.sample_uncertain \
  --weights backend/best.pt \
  --frames-source backend/data/alerts \
  --out ml/datasets/uncertain \
  --max-conf 0.6

# 2. Annotate in Label Studio (see active_learning/label_studio_setup.md)
#    Export YOLO format → ml/data/feedback/confirmed/ and ml/data/feedback/rejected/

# 3. Merge feedback into the active train split (idempotent)
bash ml/scripts/merge_feedback.sh

# 4. Retrain
bash ml/run_pipeline.sh
```

The backend can also auto-export reviewed alerts when supervisors flag them
in `/historico`. Set `VIGILANTE_RETRAINING_EXPORT_PATH=ml/data/feedback/` so
`POST /api/alerts/{id}/feedback` writes confirmed/rejected samples directly.

## Publish to Hugging Face

```bash
huggingface-cli login                        # one-time
bash ml/upload_hf.sh                         # builds model card + uploads weights
```

Repo defaults: `ROBOFLOW_API_KEY` env, `HF_REPO=badmuriss/vigilante-ppe-cctv` (override in script).

## Why retraining matters

The bootstrap `best.pt` was trained on frontal images. CCTV-mounted cameras
introduce challenges that pre-trained weights handle poorly:

- **Perspective**: helmets seen from above look different than helmets seen from
  the front. A flat circle, not a side curve.
- **Resolution**: most CCTV streams are 480p–720p, often heavily H.264
  compressed. The model must be robust to compression artifacts.
- **Lighting**: harsh sun, shadows from scaffolding, sodium lights at night.
- **Occlusion**: workers partially hidden by structures, tools, other workers.
- **Distance**: people may occupy 50×50 px patches when far from camera.

The augmentation pipeline (`augment/pipeline.py`) deliberately introduces all
of these conditions during training so the model generalizes to real-world
deployment.

## Target metrics

| Metric | Target |
|--------|--------|
| mAP@0.5 (CCTV-angle val) | ≥ 0.75 |
| Recall (per class, MVP set) | ≥ 0.85 |
| Inference latency on T4 (FP16) | ≤ 50 ms/frame |
| Inference latency on CPU (INT8) | ≤ 200 ms/frame |

## Troubleshooting

- **`torch.cuda.is_available()` returns False**: `setup_local.sh` installs the
  CUDA 12.1 wheel by default. For other CUDA versions, edit the script's
  `--index-url` to match the [PyTorch wheel index](https://pytorch.org/get-started/locally/).
- **Roboflow 401**: `export ROBOFLOW_API_KEY=...` (find it under Settings → API).
- **`weights/yolo*.pt` missing**: Ultralytics auto-downloads them on first
  `train.py` run. They land in `ml/weights/` (gitignored).
- **OOM during training**: lower `--batch 16` to `--batch 8` or reduce
  `--imgsz` in `configs/ppe-cctv-v1.yaml`.
- **Hugging Face push 403**: confirm `huggingface-cli whoami` matches the
  `HF_REPO` owner in `upload_hf.sh`.
