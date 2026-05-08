"""Merge multiple PPE datasets (SH17, SODA, CHV, Pictor-PPE) into the
6-class taxonomy used by the runtime detector.

Each source dataset has its own class index. This script:
1. Reads source dataset YAMLs to discover their class names.
2. Maps source classes to our 6-class schema (gloves, vest, eyewear, helmet,
   mask, safety_boots) using fuzzy matching on the class name.
3. Rewrites annotation files with our class indices.
4. Symlinks (or copies) images into ml/datasets/merged/{train,val,test}.

Usage:
    python -m ml.prepare.merge_datasets \
        --sources ml/datasets/sh17 ml/datasets/soda \
        --output ml/datasets/merged \
        --val-ratio 0.15 --test-ratio 0.05
"""

from __future__ import annotations

import argparse
import logging
import random
import shutil
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("merge")

# Target taxonomy — must match backend/app/detector.py::_ALL_EPI_CLASSES
# 2-class MVP: only helmet + high-visibility vest.
TARGET_CLASSES = {
    "helmet": 0,
    "vest": 1,
}

# Common synonyms found in public PPE datasets — all map to one of the two
# target classes. Anything else in the source datasets is dropped.
CLASS_ALIASES: dict[str, str] = {
    "helmet": "helmet",
    "hard_hat": "helmet",
    "hardhat": "helmet",
    "hard-hat": "helmet",
    "head_helmet": "helmet",
    "person_with_helmet": "helmet",
    "yellow_helmet": "helmet",
    "white_helmet": "helmet",
    "blue_helmet": "helmet",
    "red_helmet": "helmet",
    "vest": "vest",
    "safety_vest": "vest",
    "high_vis_vest": "vest",
    "high-vis": "vest",
    "high_visibility_vest": "vest",
    "reflective_vest": "vest",
    "hi_vis": "vest",
    "yellow_vest": "vest",
    "orange_vest": "vest",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Merge PPE datasets into 2-class schema")
    p.add_argument(
        "--sources",
        nargs="+",
        type=Path,
        required=True,
        help="Source dataset roots (each must have a data.yaml)",
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--val-ratio", type=float, default=0.15)
    p.add_argument("--test-ratio", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--copy",
        action="store_true",
        help="Copy images instead of symlinking (use on Windows or for portability)",
    )
    p.add_argument(
        "--dedupe",
        action="store_true",
        help="Skip near-duplicate images across sources via average hash",
    )
    p.add_argument(
        "--dedupe-threshold",
        type=int,
        default=4,
        help="Hamming distance threshold for dedupe (lower=stricter, default=4)",
    )
    return p.parse_args()


def _ahash(image_path: Path, hash_size: int = 16) -> int | None:
    """Average-hash for near-duplicate detection. Returns None on failure."""
    try:
        import cv2
        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        small = cv2.resize(img, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
        avg = small.mean()
        bits = (small > avg).flatten()
        h = 0
        for bit in bits:
            h = (h << 1) | int(bit)
        return h
    except Exception:
        return None


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _dedupe(
    pairs: list[tuple[Path, list[tuple[int, str]]]],
    threshold: int,
) -> list[tuple[Path, list[tuple[int, str]]]]:
    """Drop near-duplicate images (Hamming < threshold against any kept image)."""
    kept: list[tuple[Path, list[tuple[int, str]]]] = []
    kept_hashes: list[int] = []
    dropped = 0
    for img, lines in pairs:
        h = _ahash(img)
        if h is None:
            kept.append((img, lines))
            continue
        if any(_hamming(h, kh) < threshold for kh in kept_hashes):
            dropped += 1
            continue
        kept.append((img, lines))
        kept_hashes.append(h)
    logger.info("Dedupe dropped %d / %d images (threshold=%d)", dropped, len(pairs), threshold)
    return kept


def normalize_name(name: str) -> str:
    return name.lower().strip().replace(" ", "_").replace("-", "_")


_SUBSTRING_RULES: list[tuple[str, str]] = [
    # ORDER matters — longer/more-specific patterns first.
    ("hard_hat", "helmet"),
    ("hardhat", "helmet"),
    ("helmet", "helmet"),
    ("safety_vest", "vest"),
    ("hi_vis", "vest"),
    ("high_vis", "vest"),
    ("reflective_vest", "vest"),
    ("vest", "vest"),
]


def map_class(source_name: str) -> str | None:
    """Map raw source class name to one of the target classes.

    1. Try exact alias match (CLASS_ALIASES — handles canonical names).
    2. Fall back to substring contains-match (handles weird Roboflow names like
       'vest - v4 2024-05-21 1-54pm' or 'PPE_helmet_v2').
    Excludes ``no_*`` (negative class markers) so we never map them.
    """
    norm = normalize_name(source_name)
    if norm in CLASS_ALIASES:
        return CLASS_ALIASES[norm]
    if norm.startswith("no_") or norm == "-" or not norm:
        return None
    for token, target in _SUBSTRING_RULES:
        if token in norm:
            return target
    return None


def _discover_image_label_dirs(source_root: Path) -> list[tuple[Path, Path]]:
    """Return list of (images_dir, labels_dir) pairs.

    Supports two layouts:
    1. Flat: ``<root>/images/`` + ``<root>/labels/``  (some academic / our merge output)
    2. Split: ``<root>/{train,valid,val,test}/images/`` + ``.../labels/``  (Roboflow YOLOv8 export)
    """
    candidates: list[tuple[Path, Path]] = []
    flat_images = source_root / "images"
    flat_labels = source_root / "labels"
    if flat_images.is_dir() and flat_labels.is_dir():
        candidates.append((flat_images, flat_labels))

    for split in ("train", "valid", "val", "test"):
        split_images = source_root / split / "images"
        split_labels = source_root / split / "labels"
        if split_images.is_dir() and split_labels.is_dir():
            candidates.append((split_images, split_labels))

    return candidates


def collect_image_label_pairs(
    source_root: Path, source_class_map: dict[int, str]
) -> list[tuple[Path, list[tuple[int, str]]]]:
    """Returns [(image_path, [(target_class_id, yolo_line), ...])]."""
    pairs: list[tuple[Path, list[tuple[int, str]]]] = []
    dirs = _discover_image_label_dirs(source_root)
    if not dirs:
        logger.warning(
            "Source %s missing images/labels (looked for flat and train/valid/test layouts) — skipping",
            source_root,
        )
        return pairs

    for images_dir, labels_dir in dirs:
        for img in sorted(images_dir.rglob("*.jpg")) + sorted(images_dir.rglob("*.png")) + sorted(images_dir.rglob("*.jpeg")):
            rel = img.relative_to(images_dir).with_suffix(".txt")
            label = labels_dir / rel
            if not label.is_file():
                continue
            remapped: list[tuple[int, str]] = []
            for line in label.read_text().splitlines():
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                try:
                    src_idx = int(parts[0])
                except ValueError:
                    continue
                src_name = source_class_map.get(src_idx)
                if src_name is None:
                    continue
                target_name = map_class(src_name)
                if target_name is None:
                    continue
                target_idx = TARGET_CLASSES[target_name]
                remapped.append((target_idx, " ".join(parts[1:])))
            if remapped:
                pairs.append((img, remapped))
    return pairs


def write_split(
    pairs: list[tuple[Path, list[tuple[int, str]]]],
    out_root: Path,
    split: str,
    copy: bool,
) -> None:
    img_dir = out_root / "images" / split
    lbl_dir = out_root / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    for idx, (src_img, lines) in enumerate(pairs):
        # Avoid filename collisions across source datasets
        suffix = src_img.suffix
        out_img = img_dir / f"{idx:08d}{suffix}"
        out_lbl = lbl_dir / f"{idx:08d}.txt"
        if copy:
            shutil.copy(src_img, out_img)
        else:
            out_img.symlink_to(src_img.resolve())
        out_lbl.write_text(
            "\n".join(f"{cls} {rest}" for cls, rest in lines) + "\n"
        )


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    all_pairs: list[tuple[Path, list[tuple[int, str]]]] = []

    for source in args.sources:
        data_yaml = source / "data.yaml"
        if not data_yaml.is_file():
            logger.warning("Source %s missing data.yaml — skipping", source)
            continue
        cfg = yaml.safe_load(data_yaml.read_text())
        names = cfg.get("names", {})
        if isinstance(names, list):
            class_map = {i: n for i, n in enumerate(names)}
        else:
            class_map = {int(k): v for k, v in names.items()}
        pairs = collect_image_label_pairs(source, class_map)
        logger.info("Collected %d image/label pairs from %s", len(pairs), source.name)
        all_pairs.extend(pairs)

    if args.dedupe:
        all_pairs = _dedupe(all_pairs, args.dedupe_threshold)

    rng.shuffle(all_pairs)
    n = len(all_pairs)
    n_test = int(n * args.test_ratio)
    n_val = int(n * args.val_ratio)
    n_train = n - n_test - n_val

    train = all_pairs[:n_train]
    val = all_pairs[n_train : n_train + n_val]
    test = all_pairs[n_train + n_val :]

    logger.info("Splits: train=%d val=%d test=%d", len(train), len(val), len(test))

    args.output.mkdir(parents=True, exist_ok=True)
    write_split(train, args.output, "train", args.copy)
    write_split(val, args.output, "val", args.copy)
    write_split(test, args.output, "test", args.copy)

    # Write a data.yaml the YOLO loader will accept
    data_out = {
        "path": str(args.output.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {v: k for k, v in TARGET_CLASSES.items()},
    }
    (args.output / "data.yaml").write_text(yaml.safe_dump(data_out, sort_keys=False))
    logger.info("Wrote merged dataset to %s", args.output)


if __name__ == "__main__":
    main()
