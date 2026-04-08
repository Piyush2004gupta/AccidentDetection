from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Accident Detection & Emergency Response"
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    model_path: str = Field(default="lexius_accident_v1_e10.pth", alias="MODEL_PATH")
    model_type: str = Field(default="yolo", alias="MODEL_TYPE")
    device: str = Field(default="cpu", alias="MODEL_DEVICE")
    detection_confidence_threshold: float = Field(default=0.4, alias="DETECTION_CONFIDENCE_THRESHOLD")
    accident_class_index: int = Field(default=1, alias="ACCIDENT_CLASS_INDEX")

    capture_dir: str = Field(default="captures", alias="CAPTURE_DIR")
    pre_frames_count: int = Field(default=2, alias="PRE_FRAMES_COUNT")
    post_frames_count: int = Field(default=2, alias="POST_FRAMES_COUNT")
    duplicate_alert_cooldown_seconds: int = Field(default=90, alias="DUPLICATE_ALERT_COOLDOWN_SECONDS")

    cloudinary_url: str = Field(default="", alias="CLOUDINARY_URL")
    cloudinary_cloud_name: str = Field(default="", alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str = Field(default="", alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: str = Field(default="", alias="CLOUDINARY_API_SECRET")

    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_whatsapp_from: str = Field(default="", alias="TWILIO_WHATSAPP_FROM")
    twilio_phone_number: str = Field(default="", alias="TWILIO_PHONE_NUMBER")
    voice_alert_enabled: bool = Field(default=True, alias="VOICE_ALERT_ENABLED")
    voice_alert_recipients: str = Field(default="", alias="VOICE_ALERT_RECIPIENTS")

    cameras_file: str = Field(default="data/cameras.json", alias="CAMERAS_FILE")
    ambulances_file: str = Field(default="data/ambulances.json", alias="AMBULANCES_FILE")
    hospitals_file: str = Field(default="data/hospitals.json", alias="HOSPITALS_FILE")
    admins_file: str = Field(default="data/admins.json", alias="ADMINS_FILE")
    nearest_ambulance_count: int = Field(default=3, alias="NEAREST_AMBULANCE_COUNT")
    nearest_hospital_count: int = Field(default=2, alias="NEAREST_HOSPITAL_COUNT")
    alert_radius_km: float = Field(default=25.0, alias="ALERT_RADIUS_KM")
    hospital_alert_radius_km: float = Field(default=35.0, alias="HOSPITAL_ALERT_RADIUS_KM")
    
    # Default location for fallback (Google HQ, Mountain View, CA)
    default_latitude: float = Field(default=37.4220, alias="DEFAULT_LATITUDE")
    default_longitude: float = Field(default=-122.0841, alias="DEFAULT_LONGITUDE")
    # Frame detection interval in milliseconds (lower = faster, but more CPU)
    frame_detection_interval_ms: int = Field(default=200, alias="FRAME_DETECTION_INTERVAL_MS")
    # Evidence image max width for faster upload after detection
    evidence_image_max_width: int = Field(default=960, alias="EVIDENCE_IMAGE_MAX_WIDTH")

    # Allowed origins for CORS (comma-separated string)
    allowed_origins: str = Field(default="*", alias="ALLOWED_ORIGINS")

    @property
    def capture_dir_path(self) -> Path:
        return Path(self.capture_dir)

    @property
    def cameras_file_path(self) -> Path:
        return Path(self.cameras_file)

    @property
    def ambulances_file_path(self) -> Path:
        return Path(self.ambulances_file)

    @property
    def hospitals_file_path(self) -> Path:
        return Path(self.hospitals_file)

    @property
    def admins_file_path(self) -> Path:
        return Path(self.admins_file)


@lru_cache
def get_settings() -> Settings:
    return Settings()
