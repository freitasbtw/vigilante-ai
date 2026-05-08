"""Sample frames where the production model was uncertain.

Reads alert thumbnails from the production blob store, runs the current
model on each, and exports the lowest-confidence frames to a directory
suitable for ingestion into Label Studio.

Usage:
    python -m ml.active_learning.sample_uncertain \
        --weights backend/best.pt \
        --frames-dir backend/data/alerts \
        --out ml/datasets/active_learning_pool \
        --max-samples 500 \
        --max-conf 0.6
"""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("active-learning")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--frames-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-samples", type=int, default=500)
    p.add_argument(
        "--max-conf",
        type=float,
        default=0.6,
        help="Only keep frames whose top detection has confidence below this",
    )
    p.add_argument("--imgsz", type=int, default=640)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO

    model = YOLO(str(args.weights))
    candidates: list[tuple[float, Path]] = []
    frames = sorted(args.frames_dir.rglob("*_frame.jpg"))
    logger.info("Scoring %d frames", len(frames))

    for path in frames:
        results = model(str(path), imgsz=args.imgsz, verbose=False)
        max_conf = 0.0
        for result in results:
            if result.boxes is None or len(result.boxes) == 0:
                continue
            for box in result.boxes:
                max_conf = max(max_conf, float(box.conf[0].item()))
        if max_conf < args.max_conf:
            candidates.append((max_conf, path))

    candidates.sort()  # ascending — lowest confidence first
    selected = candidates[: args.max_samples]
    logger.info("Selected %d / %d candidates (max_conf < %.2f)",
                len(selected), len(candidates), args.max_conf)

    for conf, path in selected:
        out_name = f"{conf:.3f}_{path.parent.parent.name}_{path.name}"
        shutil.copy(path, args.out / out_name)

    logger.info("Wrote pool to %s — import into Label Studio for annotation", args.out)


if __name__ == "__main__":
    main()
