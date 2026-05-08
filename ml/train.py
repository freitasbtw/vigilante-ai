"""YOLOv8 training entry point.

Usage:
    python -m ml.train --config ml/configs/ppe-cctv-v1.yaml --epochs 50

Defaults to YOLOv8s (good acc/speed tradeoff for CCTV; switch to n for CPU
inference, m/l/x for GPU prod with stricter accuracy targets).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train YOLOv8 on the merged CCTV dataset")
    p.add_argument("--config", type=Path, required=True, help="YOLO data config YAML")
    p.add_argument("--model", type=str, default="yolov8s.pt", help="Base model")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--device", type=str, default="0", help="GPU id, 'cpu', or 'mps'")
    p.add_argument("--project", type=str, default="runs/train")
    p.add_argument("--name", type=str, default="ppe-cctv")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--mosaic", type=float, default=1.0, help="YOLO mosaic prob (0..1)"
    )
    p.add_argument("--mixup", type=float, default=0.1)
    p.add_argument("--workers", type=int, default=8, help="Dataloader workers")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.config.is_file():
        raise SystemExit(f"Config not found: {args.config}")

    from ultralytics import YOLO

    logger.info("Loading base model %s", args.model)
    model = YOLO(args.model)

    logger.info("Starting training: %d epochs, imgsz=%d, batch=%d", args.epochs, args.imgsz, args.batch)
    model.train(
        data=str(args.config),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=args.project,
        name=args.name,
        seed=args.seed,
        mosaic=args.mosaic,
        mixup=args.mixup,
        workers=args.workers,
        # Built-in YOLO augmentations stack with our offline Albumentations pass
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=10.0,
        translate=0.1,
        scale=0.5,
        fliplr=0.5,
        # Perspective is the key augmentation for CCTV-angle robustness
        perspective=0.0005,
    )
    logger.info("Training complete. Best weights under %s/%s/weights/best.pt", args.project, args.name)


if __name__ == "__main__":
    main()
