from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_current_user, require_role
from app.auth.router import router as auth_router
from app.config import settings
from app.db.base import dispose_engine, get_session
from app.db.entities import Camera as CameraEntity
from app.detector import EPI_CLASSES, EPI_LABELS_PT, SafetyDetector
from app.observability import configure_logging, metrics_router
from app.registry import (
    SOURCE_KIND_LOCAL,
    SOURCE_KIND_RTSP,
    StreamRegistry,
)
from app.repositories import AlertRepository, CameraRepository
from app.schemas import (
    AlertFeedbackRequest,
    AlertListResponse,
    AlertResponse,
    AlertStatusFilter,
    CameraColorConfigRequest,
    CameraColorConfigResponse,
    CameraCreateRequest,
    CameraHealthResponse,
    CameraListResponse,
    CameraResponse,
    CameraUpdateRequest,
    ClearAlertsResponse,
    COLOR_PRESETS_HSV,
    EPIConfigRequest,
    EPIConfigResponse,
    EPIItem,
    ProbeRequest,
    ProbeResponse,
    StatsResponse,
    ViolationTimelineEntry,
    hex_to_hsv_range,
    is_hex_color,
)
from app.services.retraining_exporter import RetrainingExporter
from app.sources import probe_rtsp
from app.storage import LocalBlobStore

# Deterministic id for the legacy webcam camera (auto-created on startup so the
# original single-stream endpoints keep working without a manual POST).
LEGACY_CAMERA_ID = "00000000-0000-0000-0000-000000000001"

detector = SafetyDetector()
blob_store = LocalBlobStore(settings.BLOB_STORAGE_PATH)
registry = StreamRegistry(detector, blob_store)
retraining_exporter = RetrainingExporter(blob_store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Idempotent additive migrations — keeps prod-style schema in sync without
    # pulling in alembic for the demo. Each statement is safe to re-run.
    from sqlalchemy import text as _sql_text
    from app.db.base import get_engine
    with get_engine().begin() as conn:
        conn.execute(_sql_text(
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS feedback VARCHAR(32)"
        ))
        conn.execute(_sql_text(
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS feedback_at TIMESTAMPTZ"
        ))
        conn.execute(_sql_text(
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS frame_raw_path TEXT"
        ))
        conn.execute(_sql_text(
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS detected_bboxes JSONB"
        ))
        # One-time backfill: alerts created before the soft-alert feature
        # rollout are treated as confirmed incidents (the prior behaviour).
        # New alerts (timestamp >= cutoff) stay pending until reviewed.
        # Idempotent thanks to the `feedback IS NULL` and timestamp guard.
        conn.execute(
            _sql_text(
                "UPDATE alerts SET feedback='correct' "
                "WHERE feedback IS NULL AND timestamp < :cutoff"
            ),
            {"cutoff": settings.SOFT_ALERT_FEATURE_TS},
        )
    registry.load_from_db()
    _ensure_legacy_camera()
    yield
    registry.shutdown()
    dispose_engine()


app = FastAPI(title="Vigilante.AI", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(metrics_router)


def _ensure_legacy_camera() -> CameraEntity:
    cam = registry.get_camera(LEGACY_CAMERA_ID)
    if cam is not None:
        return cam
    return registry.add_camera(
        name="Default webcam",
        source_kind=SOURCE_KIND_LOCAL,
        local_index=settings.CAMERA_INDEX,
        camera_id=LEGACY_CAMERA_ID,
    )


def _get_processor_or_404(camera_id: str):  # type: ignore[no-untyped-def]
    proc = registry.get_processor(camera_id)
    if proc is None:
        raise HTTPException(status_code=404, detail=f"Camera not found: {camera_id}")
    return proc


def _get_alert_service_or_404(camera_id: str):  # type: ignore[no-untyped-def]
    svc = registry.get_alert_service(camera_id)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"Camera not found: {camera_id}")
    return svc


def _to_camera_response(entity: CameraEntity) -> CameraResponse:
    health = registry.get_health(entity.id)
    health_resp = CameraHealthResponse(
        online=health.online if health else False,
        last_frame_at=health.last_frame_at if health else None,
        consecutive_failures=health.consecutive_failures if health else 0,
        reconnect_count=health.reconnect_count if health else 0,
        last_error=health.last_error if health else None,
    )
    return CameraResponse(
        id=entity.id,
        name=entity.name,
        source_kind=entity.source_kind,  # type: ignore[arg-type]
        rtsp_url=entity.rtsp_url,
        local_index=entity.local_index,
        location=entity.location,
        created_at=entity.created_at,
        is_running=registry.is_running(entity.id),
        health=health_resp,
    )


# --- Legacy single-stream endpoints (proxy to default camera) ---


@app.get("/api/status")
def get_status() -> dict[str, object]:
    cam = _ensure_legacy_camera()
    proc = registry.get_processor(cam.id)
    src = registry.get_source(cam.id)
    return {
        "camera_active": src.is_running if src else False,
        "model_loaded": detector.is_loaded,
        "fps": proc.fps if proc else 0.0,
        "uptime": round(proc.uptime, 1) if proc else 0.0,
    }


@app.get("/api/stream")
def get_stream() -> StreamingResponse:
    cam = _ensure_legacy_camera()
    proc = _get_processor_or_404(cam.id)
    return StreamingResponse(
        proc.generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/stream/frame")
def get_stream_frame() -> Response:
    cam = _ensure_legacy_camera()
    proc = _get_processor_or_404(cam.id)
    frame = proc.get_jpeg_frame()
    if not frame:
        raise HTTPException(status_code=503, detail="No frame available yet")
    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.post("/api/stream/start")
def start_stream() -> dict[str, str | bool]:
    cam = _ensure_legacy_camera()
    try:
        registry.start_camera(cam.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"started": True}


@app.post("/api/stream/stop")
def stop_stream() -> dict[str, bool]:
    cam = _ensure_legacy_camera()
    registry.stop_camera(cam.id)
    return {"stopped": True}


# --- New multi-camera endpoints ---


def _ensure_owns_camera(camera_id: str, user: CurrentUser) -> CameraEntity:
    """Return the camera if it belongs to the user's tenant; else 404 (not 403,
    to avoid leaking existence of cameras from other tenants)."""
    entity = registry.get_camera(camera_id, tenant_id=user.tenant_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Camera not found: {camera_id}")
    return entity


@app.get("/api/cameras", response_model=CameraListResponse)
def list_cameras(user: CurrentUser = Depends(get_current_user)) -> CameraListResponse:
    return CameraListResponse(
        cameras=[
            _to_camera_response(c)
            for c in registry.list_cameras(tenant_id=user.tenant_id)
        ]
    )


@app.post("/api/cameras", response_model=CameraResponse, status_code=201)
def create_camera(
    request: CameraCreateRequest,
    user: CurrentUser = Depends(get_current_user),
) -> CameraResponse:
    try:
        entity = registry.add_camera(
            tenant_id=user.tenant_id,
            name=request.name,
            source_kind=request.source_kind,
            rtsp_url=request.rtsp_url,
            local_index=request.local_index,
            location=request.location,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_camera_response(entity)


@app.get("/api/cameras/{camera_id}", response_model=CameraResponse)
def get_camera(
    camera_id: str, user: CurrentUser = Depends(get_current_user)
) -> CameraResponse:
    return _to_camera_response(_ensure_owns_camera(camera_id, user))


@app.patch("/api/cameras/{camera_id}", response_model=CameraResponse)
def update_camera(
    camera_id: str,
    request: CameraUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
) -> CameraResponse:
    _ensure_owns_camera(camera_id, user)
    entity = registry.update_camera(
        camera_id, name=request.name, location=request.location
    )
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Camera not found: {camera_id}")
    return _to_camera_response(entity)


@app.delete("/api/cameras/{camera_id}", status_code=204)
def delete_camera(
    camera_id: str, user: CurrentUser = Depends(get_current_user)
) -> Response:
    if camera_id == LEGACY_CAMERA_ID:
        raise HTTPException(status_code=400, detail="Cannot delete the default camera")
    _ensure_owns_camera(camera_id, user)
    if not registry.remove_camera(camera_id):
        raise HTTPException(status_code=404, detail=f"Camera not found: {camera_id}")
    return Response(status_code=204)


@app.post("/api/cameras/{camera_id}/start")
def start_camera(
    camera_id: str, user: CurrentUser = Depends(get_current_user)
) -> dict[str, bool]:
    _ensure_owns_camera(camera_id, user)
    try:
        registry.start_camera(camera_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"started": True}


@app.post("/api/cameras/{camera_id}/stop")
def stop_camera(
    camera_id: str, user: CurrentUser = Depends(get_current_user)
) -> dict[str, bool]:
    _ensure_owns_camera(camera_id, user)
    registry.stop_camera(camera_id)
    return {"stopped": True}


@app.get("/api/cameras/{camera_id}/stream/frame")
def get_camera_frame(
    camera_id: str, user: CurrentUser = Depends(get_current_user)
) -> Response:
    _ensure_owns_camera(camera_id, user)
    proc = _get_processor_or_404(camera_id)
    frame = proc.get_jpeg_frame()
    if not frame:
        raise HTTPException(status_code=503, detail="No frame available yet")
    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/api/cameras/{camera_id}/stream")
def get_camera_stream(
    camera_id: str, user: CurrentUser = Depends(get_current_user)
) -> StreamingResponse:
    _ensure_owns_camera(camera_id, user)
    proc = _get_processor_or_404(camera_id)
    return StreamingResponse(
        proc.generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/api/cameras/probe", response_model=ProbeResponse)
def probe_camera(
    request: ProbeRequest, user: CurrentUser = Depends(get_current_user)
) -> ProbeResponse:
    ok, message = probe_rtsp(request.rtsp_url, timeout_seconds=request.timeout_seconds)
    return ProbeResponse(ok=ok, message=message)


# --- Alerts (DB-backed) ---


_REVIEWER_ROLES = ("admin", "supervisor")


def _status_for(feedback: str | None) -> str:
    if feedback == "correct":
        return "confirmed"
    if feedback == "false_positive":
        return "rejected"
    return "pending"


def _alert_to_response(
    alert_id: str,
    timestamp: datetime,
    violation_type: str,
    confidence: float,
    missing_epis: list[str],
    thumbnail_path: str | None,
    frame_path: str | None,
    feedback: str | None = None,
    feedback_at: datetime | None = None,
    raw_frame_path: str | None = None,
    include_raw: bool = False,
) -> AlertResponse:
    import base64

    thumb_b64 = ""
    full_b64 = ""
    raw_b64 = ""
    if thumbnail_path:
        data = blob_store.load_bytes(thumbnail_path)
        if data:
            thumb_b64 = base64.b64encode(data).decode("utf-8")
    if frame_path:
        data = blob_store.load_bytes(frame_path)
        if data:
            full_b64 = base64.b64encode(data).decode("utf-8")
    if include_raw and raw_frame_path:
        data = blob_store.load_bytes(raw_frame_path)
        if data:
            raw_b64 = base64.b64encode(data).decode("utf-8")
    return AlertResponse(
        id=alert_id,
        timestamp=timestamp,
        violation_type=violation_type,
        confidence=confidence,
        frame_thumbnail=thumb_b64,
        frame_image=full_b64,
        frame_raw_image=raw_b64,
        missing_epis=missing_epis,
        feedback=feedback,
        feedback_at=feedback_at,
        status=_status_for(feedback),  # type: ignore[arg-type]
    )


@app.get("/api/cameras/{camera_id}/alerts", response_model=AlertListResponse)
def list_camera_alerts(
    camera_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    status: AlertStatusFilter = Query("confirmed"),
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> AlertListResponse:
    _ensure_owns_camera(camera_id, user)
    # Pending/rejected/all surface unreviewed or rejected alerts — only
    # reviewers (admin/supervisor) get to see those. Viewers always see
    # the confirmed-only feed.
    if status != "confirmed" and user.role not in _REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient role")
    repo_status = None if status == "all" else status
    rows, _total = AlertRepository(session).list_by_camera(
        camera_id, page=page, size=size, status=repo_status
    )
    include_raw = user.role in _REVIEWER_ROLES
    return AlertListResponse(
        alerts=[
            _alert_to_response(
                alert_id=a.id,
                timestamp=a.timestamp,
                violation_type=a.violation_type,
                confidence=a.confidence,
                missing_epis=a.missing_epis,
                thumbnail_path=a.thumbnail_path,
                frame_path=a.frame_path,
                feedback=a.feedback,
                feedback_at=a.feedback_at,
                raw_frame_path=a.frame_raw_path,
                include_raw=include_raw,
            )
            for a in rows
        ]
    )


@app.post("/api/alerts/{alert_id}/feedback", response_model=AlertResponse)
def post_alert_feedback(
    alert_id: str,
    request: AlertFeedbackRequest,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require_role(*_REVIEWER_ROLES)),
) -> AlertResponse:
    from app.db.entities import Alert as AlertEntity
    a = session.get(AlertEntity, alert_id)
    if a is None:
        raise HTTPException(status_code=404, detail=f"Alert not found: {alert_id}")
    _ensure_owns_camera(a.camera_id, user)
    # "none" clears feedback so the user can undo a misclick.
    a.feedback = None if request.feedback == "none" else request.feedback
    a.feedback_at = datetime.utcnow() if a.feedback else None
    session.commit()
    session.refresh(a)
    # Fire retraining export AFTER commit so a failure in disk export
    # does not roll back the human decision. Errors are logged but
    # never bubble up to the API caller.
    try:
        retraining_exporter.export(a)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Retraining export failed for alert %s", alert_id
        )
    return _alert_to_response(
        alert_id=a.id,
        timestamp=a.timestamp,
        violation_type=a.violation_type,
        confidence=a.confidence,
        missing_epis=a.missing_epis,
        thumbnail_path=a.thumbnail_path,
        frame_path=a.frame_path,
        feedback=a.feedback,
        feedback_at=a.feedback_at,
        raw_frame_path=a.frame_raw_path,
        include_raw=True,
    )


@app.delete("/api/cameras/{camera_id}/alerts", response_model=ClearAlertsResponse)
def clear_camera_alerts(
    camera_id: str,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ClearAlertsResponse:
    _ensure_owns_camera(camera_id, user)
    AlertRepository(session).delete_by_camera(camera_id)
    session.commit()
    return ClearAlertsResponse(cleared=True)


@app.get("/api/cameras/{camera_id}/stats", response_model=StatsResponse)
def get_camera_stats(
    camera_id: str,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> StatsResponse:
    _ensure_owns_camera(camera_id, user)
    repo = AlertRepository(session)
    total = repo.stats(camera_id).get("total_violations", 0)
    timeline = [
        ViolationTimelineEntry(timestamp=ts, count=count)
        for ts, count in repo.timeline_by_minute(camera_id)
    ]
    svc = registry.get_alert_service(camera_id)
    session_compliance = svc.session_compliance() if svc else {
        "compliance_rate": 100.0,
        "session_duration_seconds": 0.0,
    }
    return StatsResponse(
        total_violations=int(total),
        session_duration_seconds=float(session_compliance["session_duration_seconds"]),
        compliance_rate=float(session_compliance["compliance_rate"]),
        violations_timeline=timeline,
    )


# --- Legacy alerts/stats endpoints (proxy to default camera) ---


@app.get("/api/alerts", response_model=AlertListResponse)
def get_alerts(session: Session = Depends(get_session)) -> AlertListResponse:
    cam = _ensure_legacy_camera()
    return list_camera_alerts(cam.id, session=session)


@app.delete("/api/alerts", response_model=ClearAlertsResponse)
def clear_alerts(session: Session = Depends(get_session)) -> ClearAlertsResponse:
    cam = _ensure_legacy_camera()
    return clear_camera_alerts(cam.id, session=session)


@app.get("/api/stats", response_model=StatsResponse)
def get_stats_endpoint(
    session: Session = Depends(get_session),
) -> StatsResponse:
    cam = _ensure_legacy_camera()
    return get_camera_stats(cam.id, session=session)


# --- EPI config (per camera + legacy default) ---


_VALID_EPI_KEYS = set(EPI_CLASSES.values())


@app.get("/api/config/epis", response_model=EPIConfigResponse)
def get_epi_config() -> EPIConfigResponse:
    cam = _ensure_legacy_camera()
    proc = _get_processor_or_404(cam.id)
    active = proc.active_epis
    return EPIConfigResponse(
        epis=[
            EPIItem(key=key, label=label, active=key in active)
            for key, label in EPI_LABELS_PT.items()
        ]
    )


@app.post("/api/config/epis", response_model=EPIConfigResponse)
def post_epi_config(request: EPIConfigRequest) -> EPIConfigResponse:
    invalid = set(request.active_epis) - _VALID_EPI_KEYS
    if invalid:
        raise HTTPException(
            status_code=400, detail=f"Invalid EPI keys: {sorted(invalid)}"
        )
    cam = _ensure_legacy_camera()
    proc = _get_processor_or_404(cam.id)
    proc.set_active_epis(set(request.active_epis))
    active = proc.active_epis
    return EPIConfigResponse(
        epis=[
            EPIItem(key=key, label=label, active=key in active)
            for key, label in EPI_LABELS_PT.items()
        ]
    )


@app.get("/api/cameras/{camera_id}/config/epis", response_model=EPIConfigResponse)
def get_camera_epi_config(
    camera_id: str, user: CurrentUser = Depends(get_current_user)
) -> EPIConfigResponse:
    _ensure_owns_camera(camera_id, user)
    proc = _get_processor_or_404(camera_id)
    active = proc.active_epis
    return EPIConfigResponse(
        epis=[
            EPIItem(key=key, label=label, active=key in active)
            for key, label in EPI_LABELS_PT.items()
        ]
    )


@app.post("/api/cameras/{camera_id}/config/epis", response_model=EPIConfigResponse)
def post_camera_epi_config(
    camera_id: str,
    request: EPIConfigRequest,
    user: CurrentUser = Depends(get_current_user),
) -> EPIConfigResponse:
    _ensure_owns_camera(camera_id, user)
    invalid = set(request.active_epis) - _VALID_EPI_KEYS
    if invalid:
        raise HTTPException(
            status_code=400, detail=f"Invalid EPI keys: {sorted(invalid)}"
        )
    proc = _get_processor_or_404(camera_id)
    proc.set_active_epis(set(request.active_epis))
    active = proc.active_epis
    return EPIConfigResponse(
        epis=[
            EPIItem(key=key, label=label, active=key in active)
            for key, label in EPI_LABELS_PT.items()
        ]
    )


# --- Color palette per-camera ---


# Tracks the names the user picked per camera, so GET returns the same shape.
# The processor stores the resolved HSV ranges. No persistence — palettes
# reset on backend restart (acceptable for current MVP).
_camera_color_names: dict[str, dict[str, list[str]]] = {}


def _resolve_palette(items: list[str]) -> list[tuple[tuple[int, int, int], tuple[int, int, int]]]:
    """Accept both preset names ('amarelo') and hex codes ('#5a5a5a')."""
    out: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
    for it in items:
        if is_hex_color(it):
            try:
                out.append(hex_to_hsv_range(it))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            continue
        ranges = COLOR_PRESETS_HSV.get(it)
        if ranges is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown color '{it}'. Use a preset name or a #RRGGBB hex.",
            )
        out.extend(ranges)
    return out


@app.get(
    "/api/cameras/{camera_id}/config/colors",
    response_model=CameraColorConfigResponse,
)
def get_camera_color_config(
    camera_id: str, user: CurrentUser = Depends(get_current_user)
) -> CameraColorConfigResponse:
    _ensure_owns_camera(camera_id, user)
    _get_processor_or_404(camera_id)
    state = _camera_color_names.get(camera_id, {"capacete": [], "colete": []})
    return CameraColorConfigResponse(
        capacete=state.get("capacete", []),
        colete=state.get("colete", []),
        available_presets=sorted(COLOR_PRESETS_HSV.keys()),
    )


@app.post(
    "/api/cameras/{camera_id}/config/colors",
    response_model=CameraColorConfigResponse,
)
def post_camera_color_config(
    camera_id: str,
    request: CameraColorConfigRequest,
    user: CurrentUser = Depends(get_current_user),
) -> CameraColorConfigResponse:
    _ensure_owns_camera(camera_id, user)
    proc = _get_processor_or_404(camera_id)

    # Empty list for a class means "use global default" (None passed to processor).
    cap_names = list(request.capacete)
    vest_names = list(request.colete)
    palettes: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = {}
    if cap_names:
        palettes["capacete"] = _resolve_palette(cap_names)
    if vest_names:
        palettes["colete"] = _resolve_palette(vest_names)
    proc.set_color_palettes(palettes if palettes else None)

    _camera_color_names[camera_id] = {"capacete": cap_names, "colete": vest_names}
    return CameraColorConfigResponse(
        capacete=cap_names,
        colete=vest_names,
        available_presets=sorted(COLOR_PRESETS_HSV.keys()),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
