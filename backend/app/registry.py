"""Registry of cameras + their stream processors.

Cameras are persisted in Postgres (Phase B). The registry holds the
runtime objects (sources, processors, alert services) keyed by camera id.
On startup, `load_from_db` rehydrates the registry from the cameras table.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Sequence

from app.db.base import session_scope
from app.db.entities import Camera as CameraEntity
from app.detector import SafetyDetector
from app.repositories import CameraRepository, SiteRepository, TenantRepository
from app.services.alert_service import AlertService
from app.sources import LocalCameraSource, RTSPSource, StreamHealth, StreamSource
from app.storage import BlobStore
from app.stream import StreamProcessor

logger = logging.getLogger(__name__)


SOURCE_KIND_LOCAL = "local"
SOURCE_KIND_RTSP = "rtsp"


def _build_source(entity: CameraEntity) -> StreamSource:
    if entity.source_kind == SOURCE_KIND_LOCAL:
        if entity.local_index is None:
            raise ValueError(f"Camera {entity.id} missing local_index")
        return LocalCameraSource(index=entity.local_index, camera_id=entity.id)
    if entity.source_kind == SOURCE_KIND_RTSP:
        if not entity.rtsp_url:
            raise ValueError(f"Camera {entity.id} missing rtsp_url")
        return RTSPSource(url=entity.rtsp_url, camera_id=entity.id)
    raise ValueError(f"Unknown source_kind: {entity.source_kind}")


class StreamRegistry:
    def __init__(self, detector: SafetyDetector, blob_store: BlobStore) -> None:
        self._detector = detector
        self._blob_store = blob_store
        self._sources: dict[str, StreamSource] = {}
        self._processors: dict[str, StreamProcessor] = {}
        self._alert_services: dict[str, AlertService] = {}
        self._lock = threading.Lock()

    # --- bootstrap ---

    def load_from_db(self) -> None:
        with session_scope() as session:
            repo = CameraRepository(session)
            cameras: Sequence[CameraEntity] = repo.list_all()
            for cam in cameras:
                self._register_runtime(cam)
        logger.info(
            "Loaded %d cameras from database into registry",
            len(self._processors),
        )

    def _register_runtime(self, entity: CameraEntity) -> None:
        try:
            source = _build_source(entity)
        except Exception:
            logger.exception("Skipping camera %s: failed to build source", entity.id)
            return
        alert_service = AlertService(entity.id, self._blob_store)
        processor = StreamProcessor(
            source, self._detector, alert_service, camera_id=entity.id
        )
        from app.detector import MVP_EPI_KEYS
        processor.set_active_epis(set(MVP_EPI_KEYS))
        with self._lock:
            self._sources[entity.id] = source
            self._alert_services[entity.id] = alert_service
            self._processors[entity.id] = processor

    # --- CRUD ---

    def add_camera(
        self,
        *,
        tenant_id: str | None = None,
        name: str,
        source_kind: str,
        rtsp_url: str | None = None,
        local_index: int | None = None,
        location: str | None = None,
        camera_id: str | None = None,
    ) -> CameraEntity:
        with session_scope() as session:
            if tenant_id is None:
                tenant = TenantRepository(session).get_or_create_default()
                tenant_id = tenant.id
            site = SiteRepository(session).get_or_create_default(tenant_id)
            cam_repo = CameraRepository(session)
            entity = cam_repo.create(
                site_id=site.id,
                name=name,
                source_kind=source_kind,
                rtsp_url=rtsp_url,
                local_index=local_index,
                location=location,
                camera_id=camera_id,
            )
            session.commit()
            session.refresh(entity)
            # Detach from session before returning
            session.expunge(entity)
        with self._lock:
            if entity.id in self._processors:
                raise ValueError(f"Camera id already registered: {entity.id}")
        self._register_runtime(entity)
        logger.info("Camera added id=%s kind=%s tenant=%s", entity.id, source_kind, tenant_id)
        return entity

    def update_camera(
        self,
        camera_id: str,
        *,
        name: str | None = None,
        location: str | None = None,
    ) -> CameraEntity | None:
        with session_scope() as session:
            repo = CameraRepository(session)
            updated = repo.update(camera_id, name=name, location=location)
            if updated is None:
                return None
            session.commit()
            session.refresh(updated)
            session.expunge(updated)
            return updated

    def remove_camera(self, camera_id: str) -> bool:
        with self._lock:
            proc = self._processors.pop(camera_id, None)
            src = self._sources.pop(camera_id, None)
            self._alert_services.pop(camera_id, None)

        with session_scope() as session:
            repo = CameraRepository(session)
            removed = repo.delete(camera_id)
            session.commit()

        if proc is not None:
            try:
                proc.stop()
            except Exception:
                logger.exception("Error stopping processor for %s", camera_id)
        if src is not None and src.is_running:
            try:
                src.stop()
            except Exception:
                logger.exception("Error stopping source for %s", camera_id)
        return removed

    def list_cameras(self, tenant_id: str | None = None) -> Sequence[CameraEntity]:
        with session_scope() as session:
            repo = CameraRepository(session)
            cameras = (
                repo.list_for_tenant(tenant_id) if tenant_id else repo.list_all()
            )
            for c in cameras:
                session.expunge(c)
            return cameras

    def get_camera(
        self, camera_id: str, tenant_id: str | None = None
    ) -> CameraEntity | None:
        with session_scope() as session:
            repo = CameraRepository(session)
            cam = (
                repo.get_for_tenant(camera_id, tenant_id)
                if tenant_id
                else repo.get(camera_id)
            )
            if cam is not None:
                session.expunge(cam)
            return cam

    # --- runtime accessors ---

    def get_processor(self, camera_id: str) -> StreamProcessor | None:
        with self._lock:
            return self._processors.get(camera_id)

    def get_source(self, camera_id: str) -> StreamSource | None:
        with self._lock:
            return self._sources.get(camera_id)

    def get_alert_service(self, camera_id: str) -> AlertService | None:
        with self._lock:
            return self._alert_services.get(camera_id)

    def get_health(self, camera_id: str) -> StreamHealth | None:
        src = self.get_source(camera_id)
        return src.health if src is not None else None

    def start_camera(self, camera_id: str) -> None:
        proc = self.get_processor(camera_id)
        if proc is None:
            raise KeyError(camera_id)
        proc.start()
        # Mark active in DB
        with session_scope() as session:
            CameraRepository(session).update(
                camera_id, active=True, last_seen_at=datetime.utcnow()
            )
            session.commit()

    def stop_camera(self, camera_id: str) -> None:
        proc = self.get_processor(camera_id)
        if proc is None:
            raise KeyError(camera_id)
        proc.stop()
        with session_scope() as session:
            CameraRepository(session).update(camera_id, active=False)
            session.commit()

    def is_running(self, camera_id: str) -> bool:
        proc = self.get_processor(camera_id)
        return proc.is_running if proc is not None else False

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._processors.keys())
            procs = list(self._processors.values())
            srcs = list(self._sources.values())
            self._processors.clear()
            self._sources.clear()
            self._alert_services.clear()
        for proc in procs:
            try:
                proc.stop()
            except Exception:
                logger.exception("Error stopping processor on shutdown")
        for src in srcs:
            if src.is_running:
                try:
                    src.stop()
                except Exception:
                    logger.exception("Error stopping source on shutdown")
        logger.info("Registry shutdown complete (%d cameras)", len(ids))
