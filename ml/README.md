# Vigilante.AI — ML Training Pipeline

PPE detection model retraining for **CCTV-angle imagery** (top-down, wide-angle,
low-resolution security cameras) — distinct from frontal/selfie images that
the bootstrap `best.pt` was trained on.

## Layout

```
ml/
├── datasets/                      # Downloaded datasets (gitignored)
├── configs/
│   ├── ppe-cctv-v1.yaml           # YOLO data config (paths, classes)
│   └── augment.yaml               # Albumentations pipeline config
├── train.py                       # CLI: train YOLOv8 on the merged CCTV dataset
├── eval.py                        # mAP per class + confusion matrix
├── export.py                      # ONNX, TensorRT, INT8
├── prepare/
│   ├── DATASETS.md                # Selection guide + curl-verified URLs
│   ├── voc_to_yolo.py             # Pascal VOC → YOLO converter (SHWD, GDUT-HWD)
│   └── merge_datasets.py          # Unify class taxonomies → 2-class schema + dedupe
├── augment/
│   └── pipeline.py                # Albumentations transforms (perspective, blur, downscale)
└── active_learning/
    ├── sample_uncertain.py        # Pull low-confidence frames from production
    └── label_studio_setup.md      # How to deploy Label Studio locally
```

## Quick start

```bash
# 1. Setup local CUDA env (one-shot)
bash ml/setup_local.sh
source ml/.venv/bin/activate
python -c "import torch; print(torch.cuda.is_available())"   # expect: True

# 2. Download datasets — see prepare/DATASETS.md for the curl-verified shortlist
git clone https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset ml/datasets/shwd_raw
git clone https://github.com/wujixiu/helmet-detection ml/datasets/gdut_raw
git clone https://github.com/ciber-lab/pictor-ppe ml/datasets/pictor_ppe
# Hard Hat Workers: download manually from https://public.roboflow.com/object-detection/hard-hat-workers

# 3. Convert VOC → YOLO where needed
python -m ml.prepare.voc_to_yolo \
  --voc-root ml/datasets/shwd_raw \
  --out-root ml/datasets/shwd \
  --images-subdir VOC2028/JPEGImages \
  --annotations-subdir VOC2028/Annotations
python -m ml.prepare.voc_to_yolo --voc-root ml/datasets/gdut_raw --out-root ml/datasets/gdut

# 4. Merge into the 2-class schema with dedupe
python -m ml.prepare.merge_datasets \
  --sources ml/datasets/shwd ml/datasets/gdut ml/datasets/pictor_ppe ml/datasets/hardhat \
  --output ml/datasets/merged --dedupe

# 5. Train (RTX 4070 Super: ~3-4h for 50 epochs)
python -m ml.train --config ml/configs/ppe-cctv-v1.yaml --epochs 50 --batch 16

# 6. Eval
python -m ml.eval --weights runs/train/ppe-cctv/weights/best.pt --data ml/configs/ppe-cctv-v1.yaml

# 7. Drop into backend
cp runs/train/ppe-cctv/weights/best.pt backend/best.pt
```

## Why the model needs retraining

The current `best.pt` was trained on frontal images. CCTV-mounted cameras
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

## Active learning

After deploying the bootstrap model to a pilot site, `sample_uncertain.py`
pulls frames where the model was uncertain (low max-confidence) or where
predictions oscillated frame-to-frame. These are sent to Label Studio for
human annotation, then mixed into the next training run. See
`active_learning/label_studio_setup.md`.

## Target metrics

| Metric | Target |
|--------|--------|
| mAP@0.5 (CCTV-angle val) | ≥ 0.75 |
| Recall (per class, MVP set) | ≥ 0.85 |
| Inference latency on T4 (FP16) | ≤ 50 ms/frame |
| Inference latency on CPU (INT8) | ≤ 200 ms/frame |
