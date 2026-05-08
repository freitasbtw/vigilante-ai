"""Convert Pascal VOC dataset (XML annotations) to YOLO format.

SODA and several other academic PPE datasets ship in VOC. This script
walks the VOC layout, parses bounding boxes from XML, and writes YOLO
.txt files alongside images plus a `data.yaml` compatible with our
`merge_datasets.py`.

Usage:
    python -m ml.prepare.voc_to_yolo \
        --voc-root ml/datasets/soda \
        --out-root ml/datasets/soda_yolo
"""

from __future__ import annotations

import argparse
import logging
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("voc2yolo")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--voc-root", type=Path, required=True)
    p.add_argument("--out-root", type=Path, required=True)
    p.add_argument(
        "--images-subdir",
        type=str,
        default="JPEGImages",
        help="Image folder name under voc-root",
    )
    p.add_argument(
        "--annotations-subdir",
        type=str,
        default="Annotations",
        help="Annotation folder name under voc-root",
    )
    return p.parse_args()


def collect_classes(annotations_dir: Path) -> list[str]:
    classes: set[str] = set()
    for xml in annotations_dir.rglob("*.xml"):
        try:
            root = ET.parse(xml).getroot()
        except ET.ParseError:
            continue
        for obj in root.findall("object"):
            name_el = obj.find("name")
            if name_el is not None and name_el.text:
                classes.add(name_el.text.strip())
    return sorted(classes)


def voc_box_to_yolo(
    bbox: tuple[float, float, float, float], img_w: int, img_h: int
) -> tuple[float, float, float, float] | None:
    xmin, ymin, xmax, ymax = bbox
    if xmax <= xmin or ymax <= ymin or img_w <= 0 or img_h <= 0:
        return None
    x = (xmin + xmax) / 2.0 / img_w
    y = (ymin + ymax) / 2.0 / img_h
    w = (xmax - xmin) / img_w
    h = (ymax - ymin) / img_h
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
        return None
    return x, y, w, h


def main() -> None:
    args = parse_args()
    annotations_dir = args.voc_root / args.annotations_subdir
    images_dir = args.voc_root / args.images_subdir
    if not annotations_dir.is_dir():
        raise SystemExit(f"Missing {annotations_dir}")
    if not images_dir.is_dir():
        raise SystemExit(f"Missing {images_dir}")

    classes = collect_classes(annotations_dir)
    logger.info("Discovered %d classes: %s", len(classes), classes)
    class_to_idx = {name: i for i, name in enumerate(classes)}

    out_images = args.out_root / "images"
    out_labels = args.out_root / "labels"
    out_images.mkdir(parents=True, exist_ok=True)
    out_labels.mkdir(parents=True, exist_ok=True)

    converted = 0
    skipped = 0
    for xml in sorted(annotations_dir.rglob("*.xml")):
        try:
            root = ET.parse(xml).getroot()
        except ET.ParseError:
            skipped += 1
            continue

        size_el = root.find("size")
        if size_el is None:
            skipped += 1
            continue
        try:
            img_w = int(size_el.findtext("width") or 0)
            img_h = int(size_el.findtext("height") or 0)
        except ValueError:
            skipped += 1
            continue

        filename = (root.findtext("filename") or xml.stem + ".jpg").strip()
        src_img = images_dir / filename
        if not src_img.is_file():
            # Try common alternate extensions
            for ext in (".jpg", ".jpeg", ".png", ".JPG"):
                alt = images_dir / (xml.stem + ext)
                if alt.is_file():
                    src_img = alt
                    break
            else:
                skipped += 1
                continue

        lines: list[str] = []
        for obj in root.findall("object"):
            name = (obj.findtext("name") or "").strip()
            if not name:
                continue
            cls_idx = class_to_idx[name]
            bbox_el = obj.find("bndbox")
            if bbox_el is None:
                continue
            try:
                xmin = float(bbox_el.findtext("xmin") or 0)
                ymin = float(bbox_el.findtext("ymin") or 0)
                xmax = float(bbox_el.findtext("xmax") or 0)
                ymax = float(bbox_el.findtext("ymax") or 0)
            except ValueError:
                continue
            yolo_box = voc_box_to_yolo((xmin, ymin, xmax, ymax), img_w, img_h)
            if yolo_box is None:
                continue
            x, y, w, h = yolo_box
            lines.append(f"{cls_idx} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")

        if not lines:
            skipped += 1
            continue

        out_img = out_images / src_img.name
        if not out_img.exists():
            shutil.copy(src_img, out_img)
        (out_labels / (out_img.stem + ".txt")).write_text("\n".join(lines) + "\n")
        converted += 1

    data = {
        "path": str(args.out_root.resolve()),
        "train": "images",
        "val": "images",
        "names": {i: n for n, i in class_to_idx.items()},
    }
    (args.out_root / "data.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    logger.info("Converted %d / %d (skipped %d)", converted, converted + skipped, skipped)


if __name__ == "__main__":
    main()
