import base64
import logging
from datetime import datetime, timezone
from functools import lru_cache

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException

from app.models.schemas import DetectFrameRequest, DetectRequest, DetectionResponse, SendAlertRequest, SendVoiceCallRequest
from app.services.pipeline_service import AccidentPipelineService

logger = logging.getLogger(__name__)
router = APIRouter()


def _dispatch_message(notified_ambulances: list[str], notified_hospitals: list[str], notified_admins: list[str]) -> str:
    total = len(notified_ambulances) + len(notified_hospitals) + len(notified_admins)
    if total == 0:
        return "Accident detected, but no WhatsApp alerts were delivered. Check Twilio sandbox/credentials."
    return (
        "Accident detected and alerts dispatched "
        f"(ambulances: {len(notified_ambulances)}, hospitals: {len(notified_hospitals)}, admins: {len(notified_admins)})."
    )


@lru_cache(maxsize=1)
def get_pipeline() -> AccidentPipelineService:
    return AccidentPipelineService()


@router.post("/detect", response_model=DetectionResponse)
def detect_accident(request: DetectRequest) -> DetectionResponse:
    pipeline = get_pipeline()
    try:
        event = pipeline.process_stream(
            camera_id=request.camera_id,
            source=request.source,
            max_frames=request.max_frames,
        )
    except Exception as exc:
        logger.exception("Detection pipeline failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not event:
        lat, lon = pipeline.location_service.get_location(request.camera_id)
        return DetectionResponse(
            accident_detected=False,
            camera_id=request.camera_id,
            latitude=lat,
            longitude=lon,
            message="No accident detected in processed frames.",
        )

    return DetectionResponse(
        accident_detected=True,
        camera_id=event.camera_id,
        timestamp=event.timestamp,
        evidence_captured_at=event.evidence_captured_at,
        latitude=event.latitude,
        longitude=event.longitude,
        confidence=event.confidence,
        severity=event.severity,
        image_url=event.image_url,
        saved_images=event.local_paths,
        notified_ambulances=event.notified_ambulances,
        notified_hospitals=event.notified_hospitals,
        notified_admins=event.notified_admins,
        message=_dispatch_message(
            event.notified_ambulances,
            event.notified_hospitals,
            event.notified_admins,
        ),
    )


@router.post("/detect-frame", response_model=DetectionResponse)
def detect_from_frame(request: DetectFrameRequest) -> DetectionResponse:
    pipeline = get_pipeline()
    payload = request.image_base64.strip()
    if payload.startswith("data:"):
        try:
            payload = payload.split(",", 1)[1]
        except IndexError as exc:
            raise HTTPException(status_code=400, detail="Invalid data URL image payload") from exc

    try:
        image_bytes = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 image payload") from exc

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Failed to decode frame image")

    try:
        event = pipeline.process_frame(request.camera_id, frame)
        detection = pipeline.get_last_detection(request.camera_id)
    except Exception as exc:
        logger.exception("Frame detection pipeline failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not event:
        lat, lon = pipeline.location_service.get_location(request.camera_id)
        return DetectionResponse(
            accident_detected=False,
            camera_id=request.camera_id,
            latitude=lat,
            longitude=lon,
            detections=detection.detections if detection else [],
            frame_width=detection.frame_width if detection else int(frame.shape[1]),
            frame_height=detection.frame_height if detection else int(frame.shape[0]),
            message="No accident detected in this frame.",
        )

    return DetectionResponse(
        accident_detected=True,
        camera_id=event.camera_id,
        timestamp=event.timestamp,
        evidence_captured_at=event.evidence_captured_at,
        latitude=event.latitude,
        longitude=event.longitude,
        confidence=event.confidence,
        severity=event.severity,
        detections=detection.detections if detection else [],
        frame_width=detection.frame_width if detection else int(frame.shape[1]),
        frame_height=detection.frame_height if detection else int(frame.shape[0]),
        image_url=event.image_url,
        saved_images=event.local_paths,
        notified_ambulances=event.notified_ambulances,
        notified_hospitals=event.notified_hospitals,
        notified_admins=event.notified_admins,
        message=_dispatch_message(
            event.notified_ambulances,
            event.notified_hospitals,
            event.notified_admins,
        ),
    )


@router.post("/send-alert", response_model=DetectionResponse)
def send_alert(request: SendAlertRequest) -> DetectionResponse:
    pipeline = get_pipeline()
    if request.camera_id:
        lat, lon = pipeline.location_service.get_location(request.camera_id)
    else:
        if request.latitude is None or request.longitude is None:
            raise HTTPException(
                status_code=400,
                detail="Either camera_id or explicit latitude/longitude must be provided.",
            )
        lat = request.latitude
        lon = request.longitude

    if request.image_url:
        image_url = request.image_url
        saved_images: list[str] = []
    elif request.image_path:
        image_url = pipeline.cloudinary.upload_image(request.image_path)
        saved_images = [request.image_path]
    else:
        raise HTTPException(status_code=400, detail="image_url or image_path is required")

    timestamp = request.timestamp or datetime.now(timezone.utc)
    severity = request.severity or "medium"

    try:
        notified_ambulances, notified_hospitals, notified_admins = pipeline.send_manual_alert(
            camera_id=request.camera_id,
            latitude=lat,
            longitude=lon,
            image_url=image_url,
            severity=severity,
            timestamp=timestamp,
            whatsapp_only=request.whatsapp_only,
        )
    except Exception as exc:
        logger.exception("Manual alert flow failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DetectionResponse(
        accident_detected=True,
        camera_id=request.camera_id or "manual",
        timestamp=timestamp,
        latitude=lat,
        longitude=lon,
        confidence=None,
        severity=severity,
        image_url=image_url,
        saved_images=saved_images,
        notified_ambulances=notified_ambulances,
        notified_hospitals=notified_hospitals,
        notified_admins=notified_admins,
        message=_dispatch_message(
            notified_ambulances,
            notified_hospitals,
            notified_admins,
        ),
    )


@router.post("/send-voice-call")
def send_voice_call(request: SendVoiceCallRequest) -> dict:
    """
    Send an emergency voice call to a specific recipient.

    This endpoint allows manual triggering of emergency voice calls via Twilio.
    Voice calls provide immediate audio alerts about accident detection.

    Args:
        request: SendVoiceCallRequest with recipient details and location

    Returns:
        JSON with call status and call SID
    """
    pipeline = get_pipeline()

    if not pipeline.voice_alert:
        raise HTTPException(
            status_code=400,
            detail="Voice alerts are not enabled. Set VOICE_ALERT_ENABLED=true in .env",
        )

    timestamp = request.timestamp or datetime.now(timezone.utc)

    try:
        call_sid = pipeline.voice_alert.send_emergency_call(
            recipient_name=request.recipient_name,
            recipient_phone=request.recipient_phone,
            role=request.role,
            latitude=request.latitude,
            longitude=request.longitude,
            timestamp=timestamp,
            severity=request.severity,
        )
        return {
            "status": "success",
            "call_sid": call_sid,
            "message": f"Voice call sent to {request.recipient_name} at {request.recipient_phone}",
            "recipient_phone": request.recipient_phone,
            "role": request.role,
            "latitude": request.latitude,
            "longitude": request.longitude,
            "severity": request.severity,
            "timestamp": timestamp,
        }
    except Exception as exc:
        logger.exception("Voice call failed")
        raise HTTPException(status_code=500, detail=f"Voice call failed: {str(exc)}") from exc
