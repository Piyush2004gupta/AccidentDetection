from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

import cv2

from app.core.config import get_settings
from app.services.admin_service import AdminService
from app.services.alert_service import WhatsAppAlertService
from app.services.ambulance_service import AmbulanceService
from app.services.cloudinary_service import CloudinaryService
from app.services.detection_service import AccidentDetector, DetectionResult
from app.services.hospital_service import HospitalService
from app.services.location_service import CameraLocationService
from app.services.voice_alert_service import VoiceAlertService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AccidentEvent:
    camera_id: str
    timestamp: datetime
    evidence_captured_at: datetime
    confidence: float
    severity: str
    latitude: float
    longitude: float
    local_paths: list[str]
    image_url: str
    notified_ambulances: list[str]
    notified_hospitals: list[str]
    notified_admins: list[str]


class AccidentPipelineService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.detector: AccidentDetector | None = None
        self.location_service = CameraLocationService()
        self.ambulance_service = AmbulanceService()
        self.hospital_service = HospitalService()
        self.admin_service = AdminService()
        self.cloudinary = CloudinaryService()
        self.whatsapp = WhatsAppAlertService()
        self.voice_alert = VoiceAlertService() if self.settings.voice_alert_enabled else None
        self._last_alert_by_camera: dict[str, datetime] = {}
        self._frame_pre_buffers: dict[str, deque] = {}
        self._frame_inference_buffers: dict[str, deque] = {}
        self._last_detection_by_camera: dict[str, DetectionResult] = {}
        self.settings.capture_dir_path.mkdir(parents=True, exist_ok=True)

    def _get_detector(self) -> AccidentDetector:
        if self.detector is None:
            self.detector = AccidentDetector()
        return self.detector

    def _is_duplicate_alert(self, camera_id: str, now: datetime) -> bool:
        last = self._last_alert_by_camera.get(camera_id)
        if not last:
            return False
        delta = (now - last).total_seconds()
        return delta < self.settings.duplicate_alert_cooldown_seconds

    def process_stream(self, camera_id: str, source: str, max_frames: int = 0) -> AccidentEvent | None:
        lat, lon = self.location_service.get_location(camera_id)
        stream_source: str | int = int(source) if source.isdigit() else source
        cap = cv2.VideoCapture(stream_source)
        if not cap.isOpened():
            raise RuntimeError(f"Unable to open stream source: {source}")

        detector = self._get_detector()
        pre_buffer = deque(maxlen=self.settings.pre_frames_count)
        inference_buffer = deque(maxlen=max(1, detector.required_frames))
        frame_index = 0

        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                frame_index += 1
                pre_buffer.append(frame.copy())
                inference_buffer.append(frame.copy())

                if len(inference_buffer) < max(1, detector.required_frames):
                    if max_frames > 0 and frame_index >= max_frames:
                        break
                    continue

                detection = detector.infer(list(inference_buffer))
                if detection.accident_detected:
                    now = datetime.now(timezone.utc)
                    if self._is_duplicate_alert(camera_id, now):
                        logger.info("Duplicate alert suppressed for camera_id=%s", camera_id)
                        continue

                    local_paths = self._save_event_frames(camera_id, frame, pre_buffer, cap)
                    image_url = self.cloudinary.upload_image(local_paths[0])
                    notified_ambulances, notified_hospitals, notified_admins = self._notify_recipients(
                        lat,
                        lon,
                        now,
                        image_url,
                        detection.severity,
                    )
                    self._last_alert_by_camera[camera_id] = now
                    return AccidentEvent(
                        camera_id=camera_id,
                        timestamp=now,
                        evidence_captured_at=now,
                        confidence=detection.confidence,
                        severity=detection.severity,
                        latitude=lat,
                        longitude=lon,
                        local_paths=local_paths,
                        image_url=image_url,
                        notified_ambulances=notified_ambulances,
                        notified_hospitals=notified_hospitals,
                        notified_admins=notified_admins,
                    )

                if max_frames > 0 and frame_index >= max_frames:
                    break
        finally:
            cap.release()

        return None

    def process_frame(self, camera_id: str, frame) -> AccidentEvent | None:
        lat, lon = self.location_service.get_location(camera_id)
        detector = self._get_detector()

        pre_buffer = self._frame_pre_buffers.setdefault(
            camera_id,
            deque(maxlen=self.settings.pre_frames_count),
        )
        inference_buffer = self._frame_inference_buffers.setdefault(
            camera_id,
            deque(maxlen=max(1, detector.required_frames)),
        )

        frame_captured_at = datetime.now(timezone.utc)
        pre_buffer.append((frame_captured_at, frame.copy()))
        inference_buffer.append(frame.copy())

        if len(inference_buffer) < max(1, detector.required_frames):
            return None

        detection = detector.infer(list(inference_buffer))
        self._last_detection_by_camera[camera_id] = detection
        if not detection.accident_detected:
            return None

        now = datetime.now(timezone.utc)
        if self._is_duplicate_alert(camera_id, now):
            logger.info("Duplicate frame-alert suppressed for camera_id=%s", camera_id)
            return None

        evidence_frame, evidence_captured_at = self._select_pretrigger_evidence_frame(pre_buffer, frame, frame_captured_at)
        local_paths = self._save_primary_frame(camera_id, evidence_frame, evidence_captured_at)
        image_url = self.cloudinary.upload_image(local_paths[0])
        notified_ambulances, notified_hospitals, notified_admins = self._preview_recipients(lat, lon)
        self._notify_recipients_async(
            latitude=lat,
            longitude=lon,
            timestamp=evidence_captured_at,
            image_url=image_url,
            severity=detection.severity,
        )
        self._last_alert_by_camera[camera_id] = now
        return AccidentEvent(
            camera_id=camera_id,
            timestamp=now,
            evidence_captured_at=evidence_captured_at,
            confidence=detection.confidence,
            severity=detection.severity,
            latitude=lat,
            longitude=lon,
            local_paths=local_paths,
            image_url=image_url,
            notified_ambulances=notified_ambulances,
            notified_hospitals=notified_hospitals,
            notified_admins=notified_admins,
        )

    def get_last_detection(self, camera_id: str) -> DetectionResult | None:
        return self._last_detection_by_camera.get(camera_id)

    def _save_event_frames(self, camera_id: str, frame, pre_buffer: deque, cap: cv2.VideoCapture) -> list[str]:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        saved_paths: list[str] = []

        for idx, item in enumerate(pre_buffer):
            path = self.settings.capture_dir_path / f"{camera_id}_{ts}_pre_{idx}.jpg"
            cv2.imwrite(str(path), item)
            saved_paths.append(str(path))

        main_path = self.settings.capture_dir_path / f"{camera_id}_{ts}_accident.jpg"
        cv2.imwrite(str(main_path), frame)
        saved_paths.insert(0, str(main_path))

        for idx in range(self.settings.post_frames_count):
            ok, next_frame = cap.read()
            if not ok:
                break
            path = self.settings.capture_dir_path / f"{camera_id}_{ts}_post_{idx}.jpg"
            cv2.imwrite(str(path), next_frame)
            saved_paths.append(str(path))

        return saved_paths

    def _save_frame_event(self, camera_id: str, frame, pre_buffer: deque) -> list[str]:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        saved_paths: list[str] = []

        for idx, item in enumerate(pre_buffer):
            path = self.settings.capture_dir_path / f"{camera_id}_{ts}_pre_{idx}.jpg"
            cv2.imwrite(str(path), item)
            saved_paths.append(str(path))

        main_path = self.settings.capture_dir_path / f"{camera_id}_{ts}_accident.jpg"
        cv2.imwrite(str(main_path), frame)
        saved_paths.insert(0, str(main_path))
        return saved_paths

    def _save_primary_frame(self, camera_id: str, frame, captured_at: datetime | None = None) -> list[str]:
        ts_source = captured_at or datetime.now(timezone.utc)
        ts = ts_source.strftime("%Y%m%dT%H%M%S_%fZ")
        main_path = self.settings.capture_dir_path / f"{camera_id}_{ts}_accident.jpg"

        optimized_frame = frame
        frame_height, frame_width = frame.shape[:2]
        max_width = max(320, int(self.settings.evidence_image_max_width))
        if frame_width > max_width:
            scale = max_width / float(frame_width)
            new_size = (max_width, max(1, int(frame_height * scale)))
            optimized_frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)

        cv2.imwrite(
            str(main_path),
            optimized_frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 85],
        )
        return [str(main_path)]

    def _select_pretrigger_evidence_frame(
        self,
        pre_buffer: deque,
        fallback_frame,
        fallback_captured_at: datetime,
    ) -> tuple[any, datetime]:
        entries = list(pre_buffer)

        if len(entries) >= 2:
            candidate_time, candidate_frame = entries[-2]
            if hasattr(candidate_frame, "shape"):
                return candidate_frame, candidate_time

        if len(entries) >= 1:
            candidate_time, candidate_frame = entries[-1]
            if hasattr(candidate_frame, "shape"):
                return candidate_frame, candidate_time

        return fallback_frame, fallback_captured_at

    def _preview_recipients(self, latitude: float, longitude: float) -> tuple[list[str], list[str], list[str]]:
        nearest_ambulances = self.ambulance_service.nearest(
            latitude,
            longitude,
            top_k=self.settings.nearest_ambulance_count,
            radius_km=self.settings.alert_radius_km,
        )
        nearest_hospitals = self.hospital_service.nearest(
            latitude,
            longitude,
            top_k=self.settings.nearest_hospital_count,
            radius_km=self.settings.hospital_alert_radius_km,
        )
        admins = self.admin_service.get_all()

        ambulance_numbers = [driver.phone_number for driver, _distance in nearest_ambulances]
        hospital_numbers = [hospital.phone_number for hospital, _distance in nearest_hospitals]
        admin_numbers = [admin.phone_number for admin in admins]
        return ambulance_numbers, hospital_numbers, admin_numbers

    def _notify_recipients_async(
        self,
        *,
        latitude: float,
        longitude: float,
        timestamp: datetime,
        image_url: str,
        severity: str,
        whatsapp_only: bool = False,
    ) -> None:
        thread = threading.Thread(
            target=self._notify_recipients,
            kwargs={
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": timestamp,
                "image_url": image_url,
                "severity": severity,
                "whatsapp_only": whatsapp_only,
            },
            daemon=True,
        )
        thread.start()

    def _notify_recipients(
        self,
        latitude: float,
        longitude: float,
        timestamp: datetime,
        image_url: str,
        severity: str,
        whatsapp_only: bool = False,
    ) -> tuple[list[str], list[str], list[str]]:
        nearest_ambulances = self.ambulance_service.nearest(
            latitude,
            longitude,
            top_k=self.settings.nearest_ambulance_count,
            radius_km=self.settings.alert_radius_km,
        )

        nearest_hospitals = self.hospital_service.nearest(
            latitude,
            longitude,
            top_k=self.settings.nearest_hospital_count,
            radius_km=self.settings.hospital_alert_radius_km,
        )

        admins = self.admin_service.get_all()

        notified_ambulances: list[str] = []
        for driver, _distance in nearest_ambulances:
            try:
                self.whatsapp.send_alert(
                    recipient_name=driver.name,
                    recipient_phone=driver.phone_number,
                    role="ambulance",
                    latitude=latitude,
                    longitude=longitude,
                    timestamp=timestamp,
                    image_url=image_url,
                    severity=severity,
                )
                # Send voice call if enabled and not WhatsApp-only mode
                if self.voice_alert and not whatsapp_only:
                    try:
                        self.voice_alert.send_emergency_call(
                            recipient_name=driver.name,
                            recipient_phone=driver.phone_number,
                            role="ambulance",
                            latitude=latitude,
                            longitude=longitude,
                            timestamp=timestamp,
                            severity=severity,
                        )
                    except Exception as voice_exc:
                        logger.warning("Failed voice call for ambulance %s: %s", driver.phone_number, voice_exc)
                notified_ambulances.append(driver.phone_number)
            except Exception as exc:
                logger.warning("Failed ambulance alert for %s: %s", driver.phone_number, exc)

        notified_hospitals: list[str] = []
        for hospital, _distance in nearest_hospitals:
            try:
                self.whatsapp.send_alert(
                    recipient_name=hospital.name,
                    recipient_phone=hospital.phone_number,
                    role="hospital",
                    latitude=latitude,
                    longitude=longitude,
                    timestamp=timestamp,
                    image_url=image_url,
                    severity=severity,
                )
                # Send voice call if enabled and not WhatsApp-only mode
                if self.voice_alert and not whatsapp_only:
                    try:
                        self.voice_alert.send_emergency_call(
                            recipient_name=hospital.name,
                            recipient_phone=hospital.phone_number,
                            role="hospital",
                            latitude=latitude,
                            longitude=longitude,
                            timestamp=timestamp,
                            severity=severity,
                        )
                    except Exception as voice_exc:
                        logger.warning("Failed voice call for hospital %s: %s", hospital.phone_number, voice_exc)
                notified_hospitals.append(hospital.phone_number)
            except Exception as exc:
                logger.warning("Failed hospital alert for %s: %s", hospital.phone_number, exc)

        notified_admins: list[str] = []
        for admin in admins:
            try:
                self.whatsapp.send_alert(
                    recipient_name=admin.name,
                    recipient_phone=admin.phone_number,
                    role="admin",
                    latitude=latitude,
                    longitude=longitude,
                    timestamp=timestamp,
                    image_url=image_url,
                    severity=severity,
                )
                # Send voice call if enabled and not WhatsApp-only mode
                if self.voice_alert and not whatsapp_only:
                    try:
                        self.voice_alert.send_emergency_call(
                            recipient_name=admin.name,
                            recipient_phone=admin.phone_number,
                            role="admin",
                            latitude=latitude,
                            longitude=longitude,
                            timestamp=timestamp,
                            severity=severity,
                        )
                    except Exception as voice_exc:
                        logger.warning("Failed voice call for admin %s: %s", admin.phone_number, voice_exc)
                notified_admins.append(admin.phone_number)
            except Exception as exc:
                logger.warning("Failed admin alert for %s: %s", admin.phone_number, exc)

        return notified_ambulances, notified_hospitals, notified_admins

    def send_manual_alert(
        self,
        *,
        camera_id: str | None,
        latitude: float,
        longitude: float,
        image_url: str,
        severity: str,
        timestamp: datetime,
        whatsapp_only: bool = False,
    ) -> tuple[list[str], list[str], list[str]]:
        if camera_id:
            if self._is_duplicate_alert(camera_id, timestamp):
                logger.info("Manual duplicate alert suppressed for camera_id=%s", camera_id)
                return [], [], []
            self._last_alert_by_camera[camera_id] = timestamp

        return self._notify_recipients(latitude, longitude, timestamp, image_url, severity, whatsapp_only)
