"""Evaluate a trained model: mAP per class + confusion matrix.

Usage:
    python -m ml.eval --weights runs/train/ppe-cctv/weights/best.pt \
                       --data ml/configs/ppe-cctv-v1.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("eval")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate YOLOv8 weights on the val split")
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--device", type=str, default="0")
    p.add_argument("--split", type=str, default="val", choices=["val", "test"])
    p.add_argument("--out", type=Path, default=Path("eval_report.json"))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.weights.is_file():
        raise SystemExit(f"Weights not found: {args.weights}")
    if not args.data.is_file():
        raise SystemExit(f"Data config not found: {args.data}")

    from ultralytics import YOLO

    model = YOLO(str(args.weights))
    results = model.val(
        data=str(args.data),
        imgsz=args.imgsz,
        device=args.device,
        split=args.split,
    )

    # Aggregate per-class metrics
    names = results.names
    per_class: dict[str, dict[str, float]] = {}
    if hasattr(results.box, "ap_class_index") and hasattr(results.box, "ap50"):
        for idx, ap50 in zip(results.box.ap_class_index, results.box.ap50):
            class_name = names.get(int(idx), str(idx))
            per_class[class_name] = {"ap50": float(ap50)}

    summary = {
        "mAP50": float(results.box.map50),
        "mAP50-95": float(results.box.map),
        "precision": float(results.box.mp),
        "recall": float(results.box.mr),
        "per_class": per_class,
    }

    args.out.write_text(json.dumps(summary, indent=2))
    logger.info("Wrote %s", args.out)
    logger.info("mAP@0.5 = %.3f, mAP@0.5:0.95 = %.3f", summary["mAP50"], summary["mAP50-95"])
    for cls, metrics in per_class.items():
        logger.info("  %-20s ap50=%.3f", cls, metrics["ap50"])


if __name__ == "__main__":
    main()
