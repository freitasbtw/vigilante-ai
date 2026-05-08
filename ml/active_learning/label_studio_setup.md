# Label Studio — local annotation setup

[Label Studio](https://labelstud.io/) handles bounding-box annotation for the
active learning loop. Run it locally with Docker.

## 1. Start Label Studio

```bash
docker run -it -p 8080:8080 \
  -v $(pwd)/ml/datasets/active_learning_pool:/label-studio/data/pool \
  -v $(pwd)/.label-studio:/label-studio/data \
  heartexlabs/label-studio:latest
```

Open http://localhost:8080 — create an account.

## 2. Create a project

- **Name**: PPE Active Learning v1
- **Labeling setup → Object Detection with Bounding Boxes**
- **Classes** (must match the 6-class schema):
  - gloves
  - vest
  - eyewear
  - helmet
  - mask
  - safety_boots

## 3. Import the uncertainty pool

- Settings → Cloud Storage → Add Source Storage
- Type: **Local files**
- Absolute local path: `/label-studio/data/pool`
- **Treat every bucket object as a source file** — yes
- Sync storage

Frames appear in the queue; annotate from lowest confidence first (filename
prefix is the model's max confidence — sorting ascending shows hardest cases
on top).

## 4. Export labels

- Project → Export → **YOLO format**
- Save to `ml/datasets/active_learning_v1/`
- Run `python -m ml.prepare.merge_datasets --sources ml/datasets/sh17 ml/datasets/active_learning_v1 --output ml/datasets/merged_v2` to mix into the next training run.

## Tips

- Allocate a budget: aim for ~500 newly labeled frames per cycle, monthly.
- Track per-class recall in `ml/eval.py` output before/after each cycle —
  if a class's recall drops, oversample it in the next pull.
- Always blur faces in the source frames before annotation (LGPD compliance).
  The production blob store is already configured to strip face regions.
