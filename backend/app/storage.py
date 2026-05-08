"""Blob storage abstraction.

`LocalBlobStore` writes JPEGs to the filesystem under `BLOB_STORAGE_PATH`.
Phase B uses this; production AWS replaces it with `S3BlobStore` honoring
the same `save_jpeg` / `load_bytes` / `delete` interface.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class BlobStore(Protocol):
    def save_jpeg(self, *, camera_id: str, alert_id: str, kind: str, data: bytes) -> str:
        """Persist a JPEG and return a logical path/URI suitable for storing in DB."""

    def load_bytes(self, path: str) -> bytes | None: ...

    def delete(self, path: str) -> None: ...


class LocalBlobStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save_jpeg(self, *, camera_id: str, alert_id: str, kind: str, data: bytes) -> str:
        date_part = datetime.utcnow().strftime("%Y-%m-%d")
        subdir = self._root / camera_id / date_part
        subdir.mkdir(parents=True, exist_ok=True)
        filename = f"{alert_id}_{kind}.jpg"
        full = subdir / filename
        full.write_bytes(data)
        return str(full.relative_to(self._root))

    def load_bytes(self, path: str) -> bytes | None:
        full = self._root / path
        if not full.is_file():
            return None
        try:
            full.resolve().relative_to(self._root)
        except ValueError:
            logger.warning("Blob path traversal attempt: %s", path)
            return None
        return full.read_bytes()

    def delete(self, path: str) -> None:
        full = self._root / path
        try:
            full.resolve().relative_to(self._root)
        except ValueError:
            logger.warning("Blob path traversal attempt on delete: %s", path)
            return
        if full.is_file():
            full.unlink()
