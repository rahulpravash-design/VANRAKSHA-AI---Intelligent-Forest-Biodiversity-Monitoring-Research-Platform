"""Application settings.

Every tunable lives here and is sourced from the environment (see .env.example
at the repository root).  Settings are cached so importing modules can call
``get_settings()`` freely.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _split_csv(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in value.split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------- application
    vanraksha_env: str = "development"
    app_name: str = "VANRAKSHA AI"
    app_version: str = "1.0.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    debug: bool = True

    # ------------------------------------------------------------- database
    database_url: str = "sqlite:///./vanraksha.db"
    db_echo: bool = False

    # ------------------------------------------------------------- security
    jwt_secret: str = "insecure-development-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    password_min_length: int = 10
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60

    # --------------------------------------------------------- first admin
    bootstrap_admin_email: str = "admin@vanraksha.local"
    bootstrap_admin_password: str = "change-me-immediately"
    bootstrap_admin_name: str = "VANRAKSHA Administrator"

    # -------------------------------------------------------------- storage
    storage_backend: str = "local"
    storage_local_root: str = "./storage"
    storage_public_base_url: str = "http://localhost:8000/media"
    max_image_upload_mb: int = 15
    max_audio_upload_mb: int = 25
    allowed_image_extensions: list[str] = Field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".webp"]
    )
    allowed_audio_extensions: list[str] = Field(
        default_factory=lambda: [".wav", ".flac", ".ogg", ".mp3"]
    )
    s3_endpoint_url: str = ""
    s3_bucket: str = "vanraksha-media"
    s3_region: str = "ap-south-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    # ------------------------------------------------------------ AI engine
    ai_service_url: str = ""
    ai_service_timeout_seconds: float = 30.0
    ai_vision_backend: str = "auto"
    ai_audio_backend: str = "auto"
    ai_vision_weights: str = ""
    ai_audio_weights: str = ""
    ai_min_confidence: float = 0.45
    ai_uncertain_margin: float = 0.08

    # ------------------------------------------------- biodiversity privacy
    sensitive_location_precision_deg: float = 0.1
    public_location_precision_deg: float = 0.01

    # ---------------------------------------------------- anomaly detection
    anomaly_baseline_days: int = 90
    anomaly_window_days: int = 7
    anomaly_z_threshold: float = 3.0
    anomaly_contamination: float = 0.08

    # ------------------------------------------------------------ validators
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, value):  # noqa: ANN001
        return _split_csv(value)

    @field_validator("allowed_image_extensions", "allowed_audio_extensions", mode="before")
    @classmethod
    def _parse_extensions(cls, value):  # noqa: ANN001
        parsed = _split_csv(value)
        return [e if e.startswith(".") else f".{e}" for e in (p.lower() for p in parsed)]

    # ------------------------------------------------------------ helpers
    @property
    def is_production(self) -> bool:
        return self.vanraksha_env.lower() == "production"

    @property
    def is_testing(self) -> bool:
        return self.vanraksha_env.lower() == "test"

    @property
    def storage_root(self) -> Path:
        root = Path(self.storage_local_root)
        if not root.is_absolute():
            root = (BACKEND_ROOT / root).resolve()
        return root

    @property
    def max_image_bytes(self) -> int:
        return self.max_image_upload_mb * 1024 * 1024

    @property
    def max_audio_bytes(self) -> int:
        return self.max_audio_upload_mb * 1024 * 1024

    def warn_insecure(self) -> list[str]:
        """Return a list of configuration problems that matter in production."""
        problems: list[str] = []
        if self.is_production:
            if "change" in self.jwt_secret.lower() or len(self.jwt_secret) < 32:
                problems.append("JWT_SECRET is weak or still the placeholder value.")
            if self.debug:
                problems.append("DEBUG is enabled in production.")
            if "*" in self.cors_origins:
                problems.append("CORS_ORIGINS contains a wildcard in production.")
            if self.bootstrap_admin_password == "change-me-immediately":
                problems.append("BOOTSTRAP_ADMIN_PASSWORD is still the placeholder value.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
