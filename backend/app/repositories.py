"""Data access for cameras, sites, alerts, sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.entities import Alert, Camera, Site, Tenant


class TenantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create_default(self) -> Tenant:
        tenant = self._session.scalars(select(Tenant).limit(1)).first()
        if tenant is not None:
            return tenant
        tenant = Tenant(name="default")
        self._session.add(tenant)
        self._session.flush()
        return tenant


class SiteRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create_default(self, tenant_id: str) -> Site:
        site = self._session.scalars(
            select(Site).where(Site.tenant_id == tenant_id).limit(1)
        ).first()
        if site is not None:
            return site
        site = Site(tenant_id=tenant_id, name="Default site")
        self._session.add(site)
        self._session.flush()
        return site


class CameraRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_tenant(self, tenant_id: str) -> Sequence[Camera]:
        return self._session.scalars(
            select(Camera)
            .join(Site, Site.id == Camera.site_id)
            .where(Site.tenant_id == tenant_id)
            .order_by(Camera.created_at.asc())
        ).all()

    def list_all(self) -> Sequence[Camera]:
        return self._session.scalars(
            select(Camera).order_by(Camera.created_at.asc())
        ).all()

    def get(self, camera_id: str) -> Camera | None:
        return self._session.get(Camera, camera_id)

    def get_for_tenant(self, camera_id: str, tenant_id: str) -> Camera | None:
        return self._session.scalar(
            select(Camera)
            .join(Site, Site.id == Camera.site_id)
            .where(Camera.id == camera_id, Site.tenant_id == tenant_id)
        )

    def create(
        self,
        *,
        site_id: str,
        name: str,
        source_kind: str,
        rtsp_url: str | None = None,
        local_index: int | None = None,
        location: str | None = None,
        camera_id: str | None = None,
    ) -> Camera:
        camera = Camera(
            site_id=site_id,
            name=name,
            source_kind=source_kind,
            rtsp_url=rtsp_url,
            local_index=local_index,
            location=location,
        )
        if camera_id is not None:
            camera.id = camera_id
        self._session.add(camera)
        self._session.flush()
        return camera

    def update(
        self,
        camera_id: str,
        *,
        name: str | None = None,
        location: str | None = None,
        active: bool | None = None,
        last_seen_at: datetime | None = None,
    ) -> Camera | None:
        camera = self.get(camera_id)
        if camera is None:
            return None
        if name is not None:
            camera.name = name
        if location is not None:
            camera.location = location
        if active is not None:
            camera.active = active
        if last_seen_at is not None:
            camera.last_seen_at = last_seen_at
        self._session.flush()
        return camera

    def delete(self, camera_id: str) -> bool:
        camera = self.get(camera_id)
        if camera is None:
            return False
        self._session.delete(camera)
        self._session.flush()
        return True


class AlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        camera_id: str,
        violation_type: str,
        confidence: float,
        missing_epis: list[str],
        frame_path: str | None,
        thumbnail_path: str | None,
        frame_raw_path: str | None = None,
        detected_bboxes: list[dict] | None = None,
        alert_id: str | None = None,
    ) -> Alert:
        alert = Alert(
            camera_id=camera_id,
            violation_type=violation_type,
            confidence=confidence,
            missing_epis=missing_epis,
            frame_path=frame_path,
            thumbnail_path=thumbnail_path,
            frame_raw_path=frame_raw_path,
            detected_bboxes=detected_bboxes or [],
        )
        if alert_id is not None:
            alert.id = alert_id
        self._session.add(alert)
        self._session.flush()
        return alert

    def list_by_camera(
        self,
        camera_id: str,
        *,
        page: int = 1,
        size: int = 50,
        since: datetime | None = None,
        until: datetime | None = None,
        status: str | None = None,
    ) -> tuple[Sequence[Alert], int]:
        size = max(1, min(size, 200))
        page = max(1, page)
        stmt = select(Alert).where(Alert.camera_id == camera_id)
        count_stmt = select(func.count()).select_from(Alert).where(
            Alert.camera_id == camera_id
        )
        if since is not None:
            stmt = stmt.where(Alert.timestamp >= since)
            count_stmt = count_stmt.where(Alert.timestamp >= since)
        if until is not None:
            stmt = stmt.where(Alert.timestamp <= until)
            count_stmt = count_stmt.where(Alert.timestamp <= until)
        if status == "pending":
            stmt = stmt.where(Alert.feedback.is_(None))
            count_stmt = count_stmt.where(Alert.feedback.is_(None))
        elif status == "confirmed":
            stmt = stmt.where(Alert.feedback == "correct")
            count_stmt = count_stmt.where(Alert.feedback == "correct")
        elif status == "rejected":
            stmt = stmt.where(Alert.feedback == "false_positive")
            count_stmt = count_stmt.where(Alert.feedback == "false_positive")
        stmt = stmt.order_by(desc(Alert.timestamp)).offset((page - 1) * size).limit(size)
        rows = self._session.scalars(stmt).all()
        total = self._session.scalar(count_stmt) or 0
        return rows, int(total)

    def delete_by_camera(self, camera_id: str) -> int:
        rows = self._session.scalars(
            select(Alert).where(Alert.camera_id == camera_id)
        ).all()
        for row in rows:
            self._session.delete(row)
        self._session.flush()
        return len(rows)

    def stats(
        self, camera_id: str, *, status: str | None = "confirmed"
    ) -> dict[str, float | int]:
        stmt = select(func.count()).select_from(Alert).where(
            Alert.camera_id == camera_id
        )
        if status == "confirmed":
            stmt = stmt.where(Alert.feedback == "correct")
        elif status == "pending":
            stmt = stmt.where(Alert.feedback.is_(None))
        elif status == "rejected":
            stmt = stmt.where(Alert.feedback == "false_positive")
        total = self._session.scalar(stmt) or 0
        return {"total_violations": int(total)}

    def timeline_by_minute(
        self,
        camera_id: str,
        *,
        since: datetime | None = None,
        status: str | None = "confirmed",
    ) -> list[tuple[datetime, int]]:
        bucket = func.date_trunc("minute", Alert.timestamp).label("bucket")
        stmt = select(bucket, func.count().label("count")).where(
            Alert.camera_id == camera_id
        )
        if status == "confirmed":
            stmt = stmt.where(Alert.feedback == "correct")
        elif status == "pending":
            stmt = stmt.where(Alert.feedback.is_(None))
        elif status == "rejected":
            stmt = stmt.where(Alert.feedback == "false_positive")
        if since is not None:
            stmt = stmt.where(Alert.timestamp >= since)
        stmt = stmt.group_by(bucket).order_by(bucket.asc())
        rows = self._session.execute(stmt).all()
        return [(row.bucket, int(row.count)) for row in rows]
