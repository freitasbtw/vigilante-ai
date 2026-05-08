"""Export trained weights to deployable formats.

Usage:
    python -m ml.export --weights runs/train/ppe-cctv/weights/best.pt --format onnx
    python -m ml.export --weights runs/train/ppe-cctv/weights/best.pt --format engine --half
    python -m ml.export --weights runs/train/ppe-cctv/weights/best.pt --format onnx --int8 --data ml/configs/ppe-cctv-v1.yaml
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("export")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export YOLOv8 weights")
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument(
        "--format",
        type=str,
        required=True,
        choices=["onnx", "engine", "torchscript", "openvino", "tflite"],
    )
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--half", action="store_true", help="FP16 (TensorRT)")
    p.add_argument("--int8", action="store_true", help="INT8 quantization")
    p.add_argument("--data", type=Path, default=None, help="Required for INT8 calibration")
    p.add_argument("--device", type=str, default="0")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.weights.is_file():
        raise SystemExit(f"Weights not found: {args.weights}")
    if args.int8 and args.data is None:
        raise SystemExit("--int8 requires --data <yaml> for calibration")

    from ultralytics import YOLO

    model = YOLO(str(args.weights))
    kwargs: dict[str, object] = {
        "format": args.format,
        "imgsz": args.imgsz,
        "device": args.device,
    }
    if args.half:
        kwargs["half"] = True
    if args.int8:
        kwargs["int8"] = True
        kwargs["data"] = str(args.data)

    out = model.export(**kwargs)
    logger.info("Exported to %s", out)


if __name__ == "__main__":
    main()
