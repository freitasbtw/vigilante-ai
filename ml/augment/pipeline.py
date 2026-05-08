"""Albumentations pipeline for CCTV-angle robustness.

Applied **once** during dataset preparation (offline augmentation), not during
training. YOLO's built-in mosaic + HSV jitter run on top of these images.

Usage:
    from ml.augment.pipeline import build_pipeline, augment_image

    transform = build_pipeline("ml/configs/augment.yaml")
    augmented = augment_image(transform, image, bboxes, class_labels)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def build_pipeline(config_path: str | Path) -> Any:
    """Build an Albumentations Compose pipeline from a YAML config."""
    import albumentations as A

    cfg = yaml.safe_load(Path(config_path).read_text())

    transforms = [
        A.Perspective(**cfg["perspective"]),
        A.RandomBrightnessContrast(**cfg["random_brightness_contrast"]),
        A.RandomShadow(**cfg["random_shadow"]),
        A.MotionBlur(**cfg["motion_blur"]),
        A.Defocus(**cfg["defocus"]),
        A.Downscale(**cfg["downscale"]),
        A.CoarseDropout(**cfg["coarse_dropout"]),
    ]
    return A.Compose(
        transforms,
        bbox_params=A.BboxParams(format="yolo", label_fields=["class_labels"]),
    )


def augment_image(
    transform: Any,
    image: Any,  # numpy ndarray
    bboxes: list[list[float]],  # YOLO format: [x_center, y_center, w, h] normalized
    class_labels: list[int],
) -> dict[str, Any]:
    """Apply the pipeline to a single image + bboxes."""
    return transform(image=image, bboxes=bboxes, class_labels=class_labels)
