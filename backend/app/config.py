from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    CAMERA_INDEX: int = 0
    MODEL_PATH: str = "best.pt"
    CONFIDENCE_THRESHOLD: float = 0.15
    MODEL_INPUT_SIZE: int = 512
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALERT_COOLDOWN_SECONDS: int = 10
    CAMERA_WIDTH: int = 640
    CAMERA_HEIGHT: int = 480
    FACE_SCALE_FACTOR: float = 1.1
    FACE_MIN_NEIGHBORS: int = 5
    FACE_MIN_SIZE: int = 48
    API_KEY: str = ""
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 30

    model_config = {"env_prefix": "VIGILANTE_"}


settings = Settings()
