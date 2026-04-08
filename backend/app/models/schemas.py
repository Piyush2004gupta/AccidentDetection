from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DetectRequest(BaseModel):
    camera_id: str = Field(..., description="Configured camera identifier")
    source: str = Field(..., description="Video source: rtsp/http URL or local video file path")
    max_frames: int = Field(default=0, description="Optional frame cap. 0 means run until detection or stream ends")


class DetectFrameRequest(BaseModel):
    camera_id: str = Field(..., description="Configured camera identifier")
    image_base64: str = Field(..., description="Base64-encoded JPEG/PNG image or data URL")


class SendAlertRequest(BaseModel):
    camera_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    severity: Optional[str] = None
    timestamp: Optional[datetime] = None
    whatsapp_only: bool = Field(default=False, description="If True, send only WhatsApp alerts (skip voice calls)")


class SendVoiceCallRequest(BaseModel):
    recipient_name: str = Field(..., description="Name of the recipient (ambulance driver, hospital, admin, etc.)")
    recipient_phone: str = Field(..., description="Phone number in international format (e.g., +917428503197)")
    role: str = Field(default="ambulance", description="Role: ambulance, hospital, admin, or police")
    latitude: float = Field(..., description="Accident latitude")
    longitude: float = Field(..., description="Accident longitude")
    severity: str = Field(default="medium", description="Severity level: low, medium, high, critical")
    timestamp: Optional[datetime] = None


class DetectionResponse(BaseModel):
    accident_detected: bool
    camera_id: str
    timestamp: Optional[datetime] = None
    evidence_captured_at: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: Optional[float] = None
    severity: Optional[str] = None
    detections: list[dict] = Field(default_factory=list)
    frame_width: Optional[int] = None
    frame_height: Optional[int] = None
    image_url: Optional[str] = None
    saved_images: list[str] = Field(default_factory=list)
    notified_ambulances: list[str] = Field(default_factory=list)
    notified_hospitals: list[str] = Field(default_factory=list)
    notified_admins: list[str] = Field(default_factory=list)
    message: str
