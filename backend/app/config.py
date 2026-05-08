from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    CAMERA_INDEX: int = 0
    MODEL_PATH: str = "best.pt"
    CONFIDENCE_THRESHOLD: float = 0.10
    # Per-class confidence thresholds applied after raw inference. Helmet
    # gets a stricter floor because the model produces FPs on light-colored
    # patches (cardboard, plywood). Vest stays loose because hi-viz signal
    # is distinctive enough that low-confidence boxes are usually real.
    HELMET_CONFIDENCE_THRESHOLD: float = 0.15
    VEST_CONFIDENCE_THRESHOLD: float = 0.10
    MODEL_INPUT_SIZE: int = 960
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALERT_COOLDOWN_SECONDS: int = 10
    CAMERA_WIDTH: int = 640
    CAMERA_HEIGHT: int = 480
    FACE_DETECTION_ENABLED: bool = False
    FACE_SCALE_FACTOR: float = 1.1
    FACE_MIN_NEIGHBORS: int = 5
    FACE_MIN_SIZE: int = 48
    # Color post-filter for PPE detections — drops bboxes whose interior has
    # no overlap with the expected helmet/vest color palette (drops false
    # positives on neutral construction-site artifacts).
    PPE_COLOR_FILTER_ENABLED: bool = True
    PPE_COLOR_MIN_MATCH_RATIO: float = 0.10
    # Person detector (COCO) — enforces per-person PPE compliance instead
    # of scene-level (one helmet does not cover everyone in frame).
    PERSON_MODEL_PATH: str = "yolov8n.pt"
    PERSON_INPUT_SIZE: int = 640
    PERSON_CONFIDENCE_THRESHOLD: float = 0.55
    # Filter out person bboxes that are too small (distant noise) or too
    # squat (planks, equipment misclassified as person). A real upright
    # worker has h/w >= 1.3 and area >= 0.5% of frame.
    PERSON_MIN_AREA_RATIO: float = 0.005
    PERSON_MIN_ASPECT_RATIO: float = 1.3

    # Persistence
    DATABASE_URL: str = (
        "postgresql+psycopg2://vigilante:vigilante_dev@localhost:5432/vigilante"
    )
    BLOB_STORAGE_PATH: str = "./data/alerts"
    DB_ECHO: bool = False

    # Auth
    JWT_SECRET: str = "change-me-in-production-please"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12h
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ALLOW_OPEN_REGISTRATION: bool = True  # Phase C: first user creates the tenant

    # Soft-alert feature: cutoff timestamp before which alerts auto-confirm
    # on backend startup (one-time backfill so historic data doesn't flood
    # the pending review queue). Anything created at or after this stays
    # pending until an admin/supervisor reviews it.
    SOFT_ALERT_FEATURE_TS: str = "2026-05-08T15:00:00+00:00"
    # JPEG quality used when persisting alert frames. 95 keeps detail
    # useful for both human review and retraining without ballooning
    # storage versus default ~95.
    ALERT_JPEG_QUALITY: int = 95
    # Filesystem path where confirmed/rejected feedback exports land for
    # later merging into the YOLO training dataset.
    RETRAINING_EXPORT_PATH: str = "./ml/data/feedback"

    model_config = {"env_prefix": "VIGILANTE_"}


settings = Settings()
